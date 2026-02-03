
"""Парсер .hbk файлов (архивы документации 1С).

HBK файлы - это ZIP архивы с заголовком 1С.
Используется встроенный модуль zipfile для кроссплатформенной работы.
"""

import os
import re
import zipfile
import io
from typing import Optional, List, Dict, Any
from pathlib import Path

from src.models.doc_models import HBKFile, HBKEntry, ParsedHBK, CategoryInfo
from src.core.logging import get_logger
from src.parsers.html_parser import HTMLParser
from src.core.utils import SafeSubprocessError, validate_file_path
from src.core.constants import MAX_FILE_SIZE_MB, SUPPORTED_ENCODINGS, BATCH_SIZE

logger = get_logger(__name__)

# ZIP сигнатуры
ZIP_SIGNATURE = b'PK'  # Начало ZIP (Local File Header)
ZIP_EOCD_SIGNATURE = b'PK\x05\x06'  # End of Central Directory
ZIP_EOCD_MIN_SIZE = 22  # Минимальный размер EOCD записи


class HBKParserError(Exception):
    """Исключение для ошибок парсера HBK."""
    pass


class HBKParser:
    """Парсер .hbk архивов с документацией 1С.
    
    HBK файлы содержат ZIP архив со смещением (заголовок 1С в начале файла).
    Для работы используется встроенный модуль zipfile Python.
    """
    
    def __init__(self, max_files_per_type: Optional[int] = None, max_total_files: Optional[int] = None):
        self.supported_extensions = ['.hbk', '.zip', '.7z']
        self._zip_file: Optional[zipfile.ZipFile] = None
        self._archive_data: Optional[bytes] = None
        self._archive_path: Optional[Path] = None
        self._max_file_size = MAX_FILE_SIZE_MB * 1024 * 1024  # MB в байты
        self.html_parser = HTMLParser()  # Инициализируем HTML парсер
        
        # Параметры ограничений для тестирования
        self.max_files_per_type = max_files_per_type  # None = без ограничений
        self.max_total_files = max_total_files        # None = парсить все файлы
    
    def parse_file(self, file_path: str) -> Optional[ParsedHBK]:
        """Парсит .hbk файл и извлекает содержимое."""
        file_path = Path(file_path)
        
        # Валидация входного файла
        try:
            validate_file_path(file_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация файла не прошла: {e}")
            return None
        
        # Проверка размера файла
        if file_path.stat().st_size > self._max_file_size:
            logger.error(f"Файл слишком большой: {file_path.stat().st_size / 1024 / 1024:.1f}MB")
            return None
        
        # Создаем объект результата
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(file_path),
                size=file_path.stat().st_size,
                modified=file_path.stat().st_mtime
            )
        )
        
        try:
            # Пробуем разные методы извлечения
            entries = self._extract_archive(file_path)
            if not entries:
                result.errors.append("Не удалось извлечь файлы из архива")
                return result
            
            result.file_info.entries_count = len(entries)
            
            # Анализируем структуру и извлекаем документацию
            self._analyze_structure(entries, result)
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка парсинга файла {file_path}: {e}")
            result.errors.append(f"Ошибка парсинга: {str(e)}")
            return result
    
    def _extract_archive(self, file_path: Path) -> List[HBKEntry]:
        """Извлекает список файлов из HBK архива.
        
        HBK файлы содержат ZIP архив со смещением.
        Находим ZIP сигнатуру и открываем как обычный ZIP.
        """
        try:
            entries = self._open_hbk_as_zip(file_path)
            if entries:
                return entries
            else:
                logger.error(f"Не удалось извлечь файлы из архива: {file_path}")
                return []
        except Exception as e:
            logger.error(f"Ошибка обработки архива: {e}")
            return []
    
    def _find_zip_offset(self, data: bytes) -> int:
        """Находит смещение ZIP сигнатуры в данных.
        
        Args:
            data: Байты файла
            
        Returns:
            Смещение ZIP сигнатуры или -1 если не найдена
        """
        return data.find(ZIP_SIGNATURE)
    
    def _find_zip_end(self, data: bytes, zip_start: int) -> int:
        """Находит конец ZIP архива (после EOCD записи).
        
        HBK файлы могут содержать дополнительные данные после ZIP архива.
        Нужно найти End of Central Directory (EOCD) и вычислить конец архива.
        
        Args:
            data: Байты файла
            zip_start: Начало ZIP данных
            
        Returns:
            Позиция конца ZIP архива
        """
        # Ищем EOCD сигнатуру с конца файла (она может быть не в самом конце из-за хвоста)
        # EOCD может иметь комментарий до 65535 байт
        max_comment_size = 65535
        search_start = max(zip_start, len(data) - ZIP_EOCD_MIN_SIZE - max_comment_size)
        
        # Ищем последнее вхождение EOCD сигнатуры
        eocd_pos = data.rfind(ZIP_EOCD_SIGNATURE, search_start)
        
        if eocd_pos < 0:
            # EOCD не найден, возвращаем весь файл
            logger.warning("EOCD сигнатура не найдена, используем весь файл")
            return len(data)
        
        # EOCD структура:
        # 4 bytes: signature (PK\x05\x06)
        # 2 bytes: disk number
        # 2 bytes: disk with central directory
        # 2 bytes: entries on this disk
        # 2 bytes: total entries
        # 4 bytes: central directory size
        # 4 bytes: central directory offset
        # 2 bytes: comment length
        # n bytes: comment
        
        # Читаем длину комментария (последние 2 байта перед комментарием)
        comment_length_pos = eocd_pos + 20
        if comment_length_pos + 2 <= len(data):
            comment_length = int.from_bytes(data[comment_length_pos:comment_length_pos + 2], 'little')
            zip_end = eocd_pos + ZIP_EOCD_MIN_SIZE + comment_length
            logger.debug(f"EOCD найден на позиции {eocd_pos}, комментарий {comment_length} байт, конец ZIP: {zip_end}")
            return zip_end
        
        # Если не удалось прочитать длину комментария, используем минимальный размер
        return eocd_pos + ZIP_EOCD_MIN_SIZE
    
    def _open_hbk_as_zip(self, file_path: Path) -> List[HBKEntry]:
        """Открывает HBK файл как ZIP архив.
        
        HBK файлы содержат:
        1. Заголовок 1С (до ZIP сигнатуры)
        2. ZIP архив
        3. Дополнительные данные 1С после ZIP архива (хвост)
        
        Нужно извлечь только ZIP часть для корректного парсинга.
        
        Args:
            file_path: Путь к HBK файлу
            
        Returns:
            Список записей архива
        """
        entries = []
        
        # Читаем весь файл
        with open(file_path, 'rb') as f:
            self._archive_data = f.read()
        
        # Находим начало ZIP
        zip_start = self._find_zip_offset(self._archive_data)
        if zip_start < 0:
            raise HBKParserError(f"ZIP сигнатура не найдена в файле: {file_path}")
        
        logger.debug(f"ZIP начало: {zip_start}")
        
        # Пробуем разные варианты открытия ZIP
        zip_file = self._try_open_zip(zip_start)
        
        if not zip_file:
            raise HBKParserError(f"Не удалось открыть ZIP архив в файле: {file_path}")
        
        self._zip_file = zip_file
        self._archive_path = file_path
        
        # Получаем список файлов
        for info in self._zip_file.infolist():
            entry = HBKEntry(
                path=info.filename,
                size=info.file_size,
                is_dir=info.is_dir(),
                content=None  # Содержимое загружается по требованию
            )
            entries.append(entry)
        
        logger.info(f"Архив открыт успешно. Файлов: {len(entries)}")
        
        return entries
    
    def _try_open_zip(self, zip_start: int) -> Optional[zipfile.ZipFile]:
        """Пробует открыть ZIP архив разными способами.
        
        Args:
            zip_start: Начало ZIP данных
            
        Returns:
            ZipFile объект или None
        """
        # Способ 1: Пробуем найти конец ZIP через EOCD
        zip_end = self._find_zip_end(self._archive_data, zip_start)
        logger.debug(f"Попытка 1: ZIP данные [{zip_start}:{zip_end}], размер={zip_end - zip_start}")
        
        zip_data = io.BytesIO(self._archive_data[zip_start:zip_end])
        try:
            return zipfile.ZipFile(zip_data, 'r')
        except zipfile.BadZipFile as e:
            logger.debug(f"Попытка 1 не удалась: {e}")
        
        # Способ 2: Пробуем весь файл от ZIP начала
        logger.debug(f"Попытка 2: ZIP данные [{zip_start}:конец файла]")
        zip_data = io.BytesIO(self._archive_data[zip_start:])
        try:
            return zipfile.ZipFile(zip_data, 'r')
        except zipfile.BadZipFile as e:
            logger.debug(f"Попытка 2 не удалась: {e}")
        
        # Способ 3: Ищем все EOCD и пробуем каждый
        eocd_positions = self._find_all_eocd(self._archive_data, zip_start)
        logger.debug(f"Найдено EOCD позиций: {len(eocd_positions)}")
        
        for i, eocd_pos in enumerate(eocd_positions):
            comment_len_pos = eocd_pos + 20
            if comment_len_pos + 2 <= len(self._archive_data):
                comment_len = int.from_bytes(
                    self._archive_data[comment_len_pos:comment_len_pos + 2], 'little'
                )
                zip_end = eocd_pos + ZIP_EOCD_MIN_SIZE + comment_len
                
                logger.debug(f"Попытка 3.{i}: EOCD на {eocd_pos}, zip_end={zip_end}")
                zip_data = io.BytesIO(self._archive_data[zip_start:zip_end])
                try:
                    return zipfile.ZipFile(zip_data, 'r')
                except zipfile.BadZipFile as e:
                    logger.debug(f"Попытка 3.{i} не удалась: {e}")
        
        return None
    
    def _find_all_eocd(self, data: bytes, start: int) -> List[int]:
        """Находит все позиции EOCD сигнатур.
        
        Args:
            data: Байты файла
            start: Начало поиска
            
        Returns:
            Список позиций EOCD
        """
        positions = []
        pos = start
        while True:
            pos = data.find(ZIP_EOCD_SIGNATURE, pos)
            if pos < 0:
                break
            positions.append(pos)
            pos += 1
        return positions
    
    def _analyze_structure(self, entries: List[HBKEntry], result: ParsedHBK):
        """Анализирует структуру архива и извлекает документацию."""
        
        # Статистика
        html_files = 0
        st_files = 0
        category_files = 0
        
        # Собираем все HTML файлы
        html_entries = []
        
        for entry in entries:
            if entry.is_dir:
                continue
                
            path_parts = entry.path.replace('\\', '/').split('/')
            
            # Анализируем файлы __categories__
            if path_parts[-1] == '__categories__':
                category_files += 1
                self._parse_categories_file(entry, result)
                continue
            
            # Собираем .html файлы
            if entry.path.endswith('.html'):
                html_files += 1
                if 'objects/' in entry.path or 'objects\\' in entry.path:
                    html_entries.append(entry)
                continue
            
            # Анализируем .st файлы (шаблоны)
            if entry.path.endswith('.st'):
                st_files += 1
                continue
        
        logger.info(f"Найдено HTML файлов для парсинга: {len(html_entries)}")
        
        # Обрабатываем файлы батчами
        batch_size = BATCH_SIZE
        processed_html = 0
        
        for i in range(0, len(html_entries), batch_size):
            batch = html_entries[i:i + batch_size]
            
            # Батчевое извлечение
            filenames = [entry.path for entry in batch]
            extracted_files = self.extract_batch_files(filenames)
            
            # Парсим извлеченные файлы
            for entry in batch:
                if entry.path in extracted_files:
                    entry.content = extracted_files[entry.path]
                    self._create_document_from_html(entry, result)
                    processed_html += 1
                else:
                    logger.warning(f"Файл не извлечен: {entry.path}")
        
        logger.info(f"Обработано всего: {processed_html} HTML файлов")
        
        # Обновляем статистику
        result.stats = {
            'html_files': html_files,
            'processed_html': processed_html,
            'st_files': st_files,
            'category_files': category_files,
            'total_entries': len(entries)
        }
    
    def _create_document_from_html(self, entry: HBKEntry, result: ParsedHBK):
        """Создает документ из HTML файла, используя HTMLParser для извлечения содержимого."""
        from src.models.doc_models import Documentation, DocumentType
        
        try:
            # Определяем имя документа из пути
            path_parts = entry.path.replace('\\', '/').split('/')
            doc_name = path_parts[-1].replace('.html', '')
            
            # Определяем категорию из пути
            category = path_parts[-2] if len(path_parts) > 1 else "common"
            
            # Извлекаем содержимое HTML файла из архива
            html_content = None
            if entry.content:
                # Если содержимое уже загружено
                html_content = entry.content
            else:
                # Извлекаем содержимое по требованию
                html_content = self.extract_file_content(entry.path)
            
            if not html_content:
                logger.warning(f"Не удалось извлечь содержимое файла {entry.path}")
                return
            
            # Парсим HTML используя HTMLParser
            documentation = self.html_parser.parse_html_content(
                content=html_content,
                file_path=entry.path
            )
            
            if documentation:
                # Добавляем обработанную документацию напрямую
                result.documentation.append(documentation)
                logger.debug(f"Создан документ: {documentation.name} из файла {entry.path}")
            else:
                logger.warning(f"HTMLParser не смог обработать файл {entry.path}")
            
        except Exception as e:
            logger.warning(f"Ошибка создания документа из {entry.path}: {e}")
    
    def _parse_categories_file(self, entry: HBKEntry, result: ParsedHBK):
        """Парсит файл __categories__ для извлечения метаинформации."""
        if not entry.content:
            return
        
        try:
            # Пробуем разные кодировки
            content = None
            for encoding in SUPPORTED_ENCODINGS:
                try:
                    content = entry.content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if not content:
                logger.warning(f"Не удалось декодировать файл категорий {entry.path}")
                return
            
            # Создаем категорию
            path_parts = entry.path.replace('\\', '/').split('/')
            section_name = path_parts[-2] if len(path_parts) > 1 else "unknown"
            
            category = CategoryInfo(
                name=section_name,
                section=section_name,
                description=f"Раздел документации: {section_name}"
            )
            
            # Простой парсинг версии из содержимого
            lines = content.split('\n')
            for line in lines:
                line = line.strip()
                if 'version' in line.lower() or 'версия' in line.lower():
                    # Ищем версию типа 8.3.24
                    version_match = re.search(r'8\.\d+\.\d+', line)
                    if version_match:
                        category.version_from = version_match.group(0)
                        break
            
            result.categories[section_name] = category
            logger.debug(f"Обработана категория: {section_name}")
            
        except Exception as e:
            logger.warning(f"Ошибка парсинга файла категорий {entry.path}: {e}")
    
    
    def extract_file_content(self, filename: str) -> Optional[bytes]:
        """Извлекает содержимое конкретного файла из архива.
        
        Args:
            filename: Имя файла в архиве
            
        Returns:
            Байты содержимого файла или None при ошибке
        """
        if not self._zip_file:
            logger.error("Архив не был проинициализирован")
            return None
        
        try:
            return self._zip_file.read(filename)
        except KeyError:
            logger.warning(f"Файл не найден в архиве: {filename}")
            return None
        except Exception as e:
            logger.error(f"Ошибка извлечения файла {filename}: {e}")
            return None
    
    def extract_batch_files(self, filenames: List[str]) -> Dict[str, bytes]:
        """
        Извлекает несколько файлов из архива.
        
        Args:
            filenames: Список имен файлов для извлечения
            
        Returns:
            Словарь {filename: content} с содержимым извлеченных файлов
        """
        if not self._zip_file:
            logger.error("Архив не был проинициализирован")
            return {}
        
        if not filenames:
            return {}
        
        extracted_files = {}
        
        for filename in filenames:
            try:
                content = self._zip_file.read(filename)
                extracted_files[filename] = content
            except KeyError:
                logger.warning(f"Файл не найден в архиве: {filename}")
            except Exception as e:
                logger.warning(f"Ошибка извлечения файла {filename}: {e}")
        
        return extracted_files
    
    def get_supported_files(self, directory: str) -> List[str]:
        """Возвращает список поддерживаемых файлов в директории."""
        supported_files = []
        
        if not os.path.exists(directory):
            return supported_files
        
        for file_name in os.listdir(directory):
            file_path = os.path.join(directory, file_name)
            if os.path.isfile(file_path):
                file_ext = os.path.splitext(file_name)[1].lower()
                if file_ext in self.supported_extensions:
                    supported_files.append(file_path)
        
        return supported_files

    def parse_single_file_from_archive(self, archive_path: str, target_file_path: str) -> Optional[ParsedHBK]:
        """
        Извлекает и парсит один конкретный файл из архива.
        
        Args:
            archive_path: Путь к архиву .hbk
            target_file_path: Путь к файлу внутри архива (например: "Global context/methods/catalog4838/StrLen912.html")
        
        Returns:
            ParsedHBK объект с одним файлом или None при ошибке
        """
        archive_path = Path(archive_path)
        
        try:
            # Валидация входного файла
            validate_file_path(archive_path, self.supported_extensions)
        except SafeSubprocessError as e:
            logger.error(f"Валидация архива не прошла: {e}")
            return None
        
        # Создаем объект результата
        result = ParsedHBK(
            file_info=HBKFile(
                path=str(archive_path),
                size=archive_path.stat().st_size,
                modified=archive_path.stat().st_mtime
            )
        )
        
        try:
            # Открываем архив
            self._open_hbk_as_zip(archive_path)
            
            logger.info(f"Извлечение одного файла: {target_file_path}")
            
            # Извлекаем содержимое конкретного файла
            content = self.extract_file_content(target_file_path)
            if not content:
                result.errors.append(f"Не удалось извлечь файл: {target_file_path}")
                return result
            
            logger.info(f"Файл извлечен: {len(content)} байт")
            
            # Парсим HTML содержимое если это HTML файл
            if target_file_path.lower().endswith('.html'):
                try:
                    # Декодируем содержимое
                    html_content = content.decode('utf-8', errors='ignore')
                    
                    # Парсим через HTML парсер
                    parsed_doc = self.html_parser.parse_html_content(html_content, target_file_path)
                    
                    if parsed_doc:
                        result.documents.append(parsed_doc)
                        result.file_info.entries_count = 1
                        logger.info(f"Документ успешно распарсен: {parsed_doc.name}")
                    else:
                        result.errors.append(f"Не удалось распарсить HTML: {target_file_path}")
                        
                except Exception as e:
                    logger.error(f"Ошибка парсинга HTML {target_file_path}: {e}")
                    result.errors.append(f"Ошибка парсинга HTML: {str(e)}")
            else:
                result.errors.append(f"Файл не является HTML: {target_file_path}")
            
            return result
            
        except Exception as e:
            logger.error(f"Ошибка извлечения файла {target_file_path} из {archive_path}: {e}")
            result.errors.append(f"Ошибка извлечения: {str(e)}")
            return result
    
    def close(self):
        """Закрывает открытый архив и освобождает ресурсы."""
        if self._zip_file:
            try:
                self._zip_file.close()
            except Exception:
                pass
            self._zip_file = None
        self._archive_data = None
        self._archive_path = None
    
    def __enter__(self):
        """Поддержка контекстного менеджера."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Автоматическое закрытие при выходе из контекста."""
        self.close()
        return False
