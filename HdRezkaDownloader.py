import os
import sys
import json
import time
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Union
from urllib.parse import urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from HdRezkaApi import HdRezkaApi
from HdRezkaApi.types import TVSeries, Movie
from tqdm import tqdm
from colorama import init, Fore, Style
import concurrent.futures
from threading import Lock

# Инициализация colorama
init()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('hdrezka_downloader.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы
DEFAULT_DOWNLOAD_DIR = "Videos"
CONFIG_DIR = Path.home() / "Documents" / "HdRezkaDownloader"
CONFIG_FILE = CONFIG_DIR / "downloader_config.json"
MAX_RETRIES = 3
CHUNK_SIZE = 8192
TIMEOUT = 30
MAX_WORKERS = 4

class DownloadConfig:
    """Конфигурация для скачивания"""
    def __init__(self):
        self.download_dir = DEFAULT_DOWNLOAD_DIR
        self.max_retries = MAX_RETRIES
        self.chunk_size = CHUNK_SIZE
        self.timeout = TIMEOUT
        self.max_workers = MAX_WORKERS
        self.preferred_quality = None
        self.preferred_translator = None
        self.auto_select_single_option = True
        self.auto_reload = False  # Новая настройка
        
    def load_config(self):
        """Загрузка конфигурации из файла"""
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    config_data = json.load(f)
                    for key, value in config_data.items():
                        if hasattr(self, key):
                            setattr(self, key, value)
                logger.info("Конфигурация загружена из файла")
            else:
                # Создаем конфигурацию по умолчанию
                self.save_config()
                logger.info("Создана конфигурация по умолчанию")
        except Exception as e:
            logger.warning(f"Не удалось загрузить конфигурацию: {e}")
            self.save_config()
    
    def save_config(self):
        """Сохранение конфигурации в файл"""
        try:
            # Создаем директорию если не существует
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            
            config_data = {
                'download_dir': self.download_dir,
                'max_retries': self.max_retries,
                'chunk_size': self.chunk_size,
                'timeout': self.timeout,
                'max_workers': self.max_workers,
                'preferred_quality': self.preferred_quality,
                'preferred_translator': self.preferred_translator,
                'auto_select_single_option': self.auto_select_single_option,
                'auto_reload': self.auto_reload
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)
            logger.info("Конфигурация сохранена в файл")
        except Exception as e:
            logger.warning(f"Не удалось сохранить конфигурацию: {e}")

class DownloadManager:
    """Менеджер скачивания с улучшенной обработкой ошибок и параллельностью"""
    
    def __init__(self, config: DownloadConfig):
        self.config = config
        self.session = self._create_session()
        self.download_lock = Lock()
        self.stats = {
            'total_downloads': 0,
            'successful_downloads': 0,
            'failed_downloads': 0,
            'total_bytes': 0
        }
    
    def _create_session(self) -> requests.Session:
        """Создание сессии с повторными попытками"""
        session = requests.Session()
        retry_strategy = Retry(
            total=self.config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def download_file(self, url: str, filepath: str, description: str = "") -> Tuple[bool, str]:
        """Скачивание файла с прогресс-баром"""
        try:
            # Проверяем, существует ли файл
            if os.path.exists(filepath):
                logger.info(f"Файл уже существует: {filepath}")
                return True, "Файл уже существует"
            
            # Создаем директорию если не существует
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            
            # Получаем заголовки для определения размера
            head_response = self.session.head(url, timeout=self.config.timeout)
            head_response.raise_for_status()
            
            total_size = int(head_response.headers.get('content-length', 0))
            
            # Скачиваем файл
            response = self.session.get(url, stream=True, timeout=self.config.timeout)
            response.raise_for_status()
            
            with open(filepath, 'wb') as f:
                with tqdm(
                    desc=description or os.path.basename(filepath),
                    total=total_size,
                    unit='B',
                    unit_scale=True,
                    unit_divisor=1024,
                    colour='green'
                ) as pbar:
                    for chunk in response.iter_content(chunk_size=self.config.chunk_size):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))
                            
                            with self.download_lock:
                                self.stats['total_bytes'] += len(chunk)
            
            with self.download_lock:
                self.stats['successful_downloads'] += 1
            
            logger.info(f"Файл успешно скачан: {filepath}")
            return True, "Успешно"
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Ошибка сети при скачивании {url}: {e}")
            return False, f"Ошибка сети: {e}"
        except Exception as e:
            logger.error(f"Общая ошибка при скачивании {url}: {e}")
            return False, f"Ошибка: {e}"
        finally:
            with self.download_lock:
                self.stats['total_downloads'] += 1

def clear_console():
    """Очищает консоль"""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_user_choice(prompt: str, max_value: int) -> int:
    """Получает выбор пользователя с валидацией"""
    while True:
        try:
            choice = int(input(prompt))
            if 0 <= choice <= max_value:
                return choice
            else:
                print(f"{Fore.RED}Введите число от 0 до {max_value}{Style.RESET_ALL}")
        except ValueError:
            print(f"{Fore.RED}Введите корректное число{Style.RESET_ALL}")
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Операция прервана пользователем{Style.RESET_ALL}")
            sys.exit(0)

def show_settings_menu(config: DownloadConfig):
    """Показывает меню настроек"""
    while True:
        clear_console()
        print(f"{Fore.CYAN}=== НАСТРОЙКИ ==={Style.RESET_ALL}")
        print(f"{Fore.GREEN}[1] Выйти{Style.RESET_ALL}")
        auto_reload_status = "On" if config.auto_reload else "Off"
        print(f"{Fore.GREEN}[2] Автоматическая перезагрузка : {auto_reload_status}{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[3] Тест{Style.RESET_ALL}")
        
        choice = get_user_choice(f"\n{Fore.YELLOW}Выберите опцию: {Style.RESET_ALL}", 3)
        
        if choice == 1:
            # Выход из настроек
            break
        elif choice == 2:
            # Переключение автоматической перезагрузки
            config.auto_reload = not config.auto_reload
            config.save_config()
            status = "включена" if config.auto_reload else "выключена"
            print(f"{Fore.GREEN}Автоматическая перезагрузка {status}{Style.RESET_ALL}")
            time.sleep(1)
        elif choice == 3:
            # Тест функция
            print(f"{Fore.CYAN}Тестовая функция выполнена!{Style.RESET_ALL}")
            input(f"{Fore.YELLOW}Нажмите Enter для продолжения...{Style.RESET_ALL}")

def auto_reload_functionality(config: DownloadConfig):
    """Функционал автоматической перезагрузки"""
    if config.auto_reload:
        print(f"{Fore.CYAN}Автоматическая перезагрузка включена{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Перезапуск программы через 3 секунды...{Style.RESET_ALL}")
        time.sleep(3)
        # Перезапуск программы
        python = sys.executable
        os.execl(python, python, *sys.argv)
    else:
        print(f"{Fore.YELLOW}Программа завершена. Нажмите Enter для выхода...{Style.RESET_ALL}")
        input()

def sanitize_filename(filename: str) -> str:
    """Очищает имя файла от недопустимых символов"""
    invalid_chars = '<>:"/\\|?*'
    for char in invalid_chars:
        filename = filename.replace(char, '_')
    return filename.strip()

def get_quality_priority(quality: str) -> int:
    """Возвращает приоритет качества для сортировки"""
    quality_map = {
        '2160p': 5, '4K': 5,
        '1440p': 4, '2K': 4,
        '1080p': 3, 'FHD': 3,
        '720p': 2, 'HD': 2,
        '480p': 1, 'SD': 1,
        '360p': 0
    }
    
    for key, value in quality_map.items():
        if key in quality:
            return value
    return 0

def select_translator(translators: Dict, config: DownloadConfig, auto_select: bool = True) -> str:
    """Выбор переводчика с учетом предпочтений"""
    if not translators:
        raise ValueError("Нет доступных переводчиков")
    
    # Если только один переводчик и включено автовыбор
    if len(translators) == 1 and auto_select:
        translator_id = list(translators.keys())[0]
        translator_name = translators[translator_id].get("name", "Без названия")
        print(f"{Fore.BLUE}Автоматически выбран перевод: {translator_name}{Style.RESET_ALL}")
        return translator_id
    
    # Проверяем предпочтительный переводчик
    if config.preferred_translator:
        for tid, data in translators.items():
            if config.preferred_translator in data.get("name", ""):
                print(f"{Fore.BLUE}Выбран предпочтительный перевод: {data.get('name', 'Без названия')}{Style.RESET_ALL}")
                return tid
    
    # Показываем список для выбора
    print(f"{Fore.MAGENTA}Доступные озвучки:{Style.RESET_ALL}")
    translator_list = list(translators.items())
    for i, (tid, translator) in enumerate(translator_list, 1):
        name = translator.get("name", "Без названия")
        premium_status = " (Премиум)" if translator.get("premium") else ""
        print(f"{Fore.GREEN}[{i}] {name}{premium_status}{Style.RESET_ALL}")
    
    choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер озвучки: {Style.RESET_ALL}", len(translator_list))
    return translator_list[choice - 1][0]

def select_quality(qualities: List[str], config: DownloadConfig, auto_select: bool = True) -> str:
    """Выбор качества с учетом предпочтений"""
    if not qualities:
        raise ValueError("Нет доступных качеств")
    
    # Сортируем качества по приоритету
    sorted_qualities = sorted(qualities, key=get_quality_priority, reverse=True)
    
    # Если только одно качество и включено автовыбор
    if len(sorted_qualities) == 1 and auto_select:
        print(f"{Fore.BLUE}Автоматически выбрано качество: {sorted_qualities[0]}{Style.RESET_ALL}")
        return sorted_qualities[0]
    
    # Проверяем предпочтительное качество
    if config.preferred_quality and config.preferred_quality in qualities:
        print(f"{Fore.BLUE}Выбрано предпочтительное качество: {config.preferred_quality}{Style.RESET_ALL}")
        return config.preferred_quality
    
    # Показываем список для выбора
    print(f"{Fore.MAGENTA}Доступные качества:{Style.RESET_ALL}")
    for i, quality in enumerate(sorted_qualities, 1):
        print(f"{Fore.GREEN}[{i}] {quality}{Style.RESET_ALL}")
    
    choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер качества: {Style.RESET_ALL}", len(sorted_qualities))
    return sorted_qualities[choice - 1]

def process_movie(rezka: HdRezkaApi, config: DownloadConfig, download_manager: DownloadManager, 
                 movie_title: str) -> bool:
    """Обработка фильма с исправленной логикой"""
    try:
        # Получаем информацию о переводах - для фильмов используем translators
        translations = {}
        if hasattr(rezka, 'translators') and rezka.translators:
            translations = rezka.translators
        else:
            logger.error("Нет доступных переводов для фильма")
            return False
        
        # Выбираем переводчика
        translator_id = select_translator(translations, config)
        
        # Получаем поток для фильма (без указания сезона и эпизода)
        stream = rezka.getStream(translation=translator_id)
        if not stream or not hasattr(stream, 'videos'):
            logger.error("Не удалось получить поток для фильма")
            return False
        
        # Выбираем качество
        qualities = list(stream.videos.keys())
        selected_quality = select_quality(qualities, config)
        
        # Получаем URL для скачивания
        if selected_quality not in stream.videos:
            logger.error(f"Качество '{selected_quality}' недоступно")
            return False
        
        video_url = stream.videos[selected_quality][0]
        
        # Создаем имя файла
        safe_title = sanitize_filename(movie_title)
        filename = f"{safe_title}_{selected_quality}.mp4"
        
        # Создаем путь для скачивания
        folder_path = Path(config.download_dir) / safe_title
        folder_path.mkdir(parents=True, exist_ok=True)
        filepath = folder_path / filename
        
        # Скачиваем
        print(f"{Fore.CYAN}Скачивание фильма: {movie_title}{Style.RESET_ALL}")
        success, message = download_manager.download_file(
            video_url, str(filepath), f"{safe_title} ({selected_quality})"
        )
        
        if success:
            print(f"{Fore.GREEN}Фильм успешно скачан: {filename}{Style.RESET_ALL}")
            return True
        else:
            logger.error(f"Ошибка скачивания фильма: {message}")
            return False
            
    except Exception as e:
        logger.error(f"Ошибка при обработке фильма: {e}")
        return False

def process_series(rezka: HdRezkaApi, config: DownloadConfig, download_manager: DownloadManager, 
                  series_title: str) -> bool:
    """Обработка сериала с улучшенной логикой"""
    try:
        # Получаем информацию о сериале
        if not hasattr(rezka, 'seriesInfo') or not rezka.seriesInfo:
            logger.error("Нет информации о сериале")
            return False
        
        # Собираем информацию о сезонах и эпизодах
        all_seasons = {}
        for translator_id, data in rezka.seriesInfo.items():
            episodes = data.get('episodes', {})
            for season_num, season_episodes in episodes.items():
                if season_num not in all_seasons:
                    all_seasons[season_num] = set()
                all_seasons[season_num].update(season_episodes.keys())
        
        # Конвертируем в отсортированные списки
        for season in all_seasons:
            all_seasons[season] = sorted(all_seasons[season])
        
        # Выбор сезона/эпизода
        sorted_seasons = sorted(all_seasons.keys())
        
        print(f"{Fore.MAGENTA}Доступные сезоны:{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[0] Все сезоны{Style.RESET_ALL}")
        for i, season in enumerate(sorted_seasons, 1):
            episode_count = len(all_seasons[season])
            print(f"{Fore.GREEN}[{i}] Сезон {season} ({episode_count} эпизодов){Style.RESET_ALL}")
        
        season_choice = get_user_choice(f"\n{Fore.YELLOW}Выберите сезон: {Style.RESET_ALL}", len(sorted_seasons))
        
        # Определяем эпизоды для скачивания
        episodes_to_download = []
        
        if season_choice == 0:
            # Все сезоны
            for season in sorted_seasons:
                for episode in all_seasons[season]:
                    episodes_to_download.append((season, episode))
        else:
            # Конкретный сезон
            selected_season = sorted_seasons[season_choice - 1]
            season_episodes = all_seasons[selected_season]
            
            print(f"{Fore.MAGENTA}Эпизоды сезона {selected_season}:{Style.RESET_ALL}")
            print(f"{Fore.GREEN}[0] Все эпизоды{Style.RESET_ALL}")
            for i, episode in enumerate(season_episodes, 1):
                print(f"{Fore.GREEN}[{i}] Эпизод {episode}{Style.RESET_ALL}")
            
            episode_choice = get_user_choice(f"\n{Fore.YELLOW}Выберите эпизод: {Style.RESET_ALL}", len(season_episodes))
            
            if episode_choice == 0:
                # Все эпизоды сезона
                for episode in season_episodes:
                    episodes_to_download.append((selected_season, episode))
            else:
                # Конкретный эпизод
                selected_episode = season_episodes[episode_choice - 1]
                episodes_to_download.append((selected_season, selected_episode))
        
        # Находим подходящие переводчики
        valid_translators = {}
        for tid, data in rezka.seriesInfo.items():
            translator_episodes = data.get('episodes', {})
            has_all_episodes = True
            
            for season, episode in episodes_to_download:
                if season not in translator_episodes or episode not in translator_episodes[season]:
                    has_all_episodes = False
                    break
            
            if has_all_episodes:
                valid_translators[tid] = data
        
        if not valid_translators:
            logger.error("Нет переводчиков с необходимыми эпизодами")
            return False
        
        # Преобразуем формат для функции select_translator
        formatted_translators = {}
        for tid, data in valid_translators.items():
            formatted_translators[tid] = {
                "name": data.get("translator_name", "Без названия"),
                "premium": data.get("premium", False)
            }
        
        # Выбираем переводчика
        translator_id = select_translator(formatted_translators, config)
        
        # Получаем тестовый поток для определения качества
        test_season, test_episode = episodes_to_download[0]
        test_stream = rezka.getStream(test_season, test_episode, translation=translator_id)
        
        if not test_stream or not hasattr(test_stream, 'videos'):
            logger.error("Не удалось получить тестовый поток")
            return False
        
        # Выбираем качество
        qualities = list(test_stream.videos.keys())
        selected_quality = select_quality(qualities, config)
        
        # Создаем папку для скачивания
        safe_title = sanitize_filename(series_title)
        folder_path = Path(config.download_dir) / safe_title
        folder_path.mkdir(parents=True, exist_ok=True)
        
        # Скачиваем эпизоды
        print(f"{Fore.CYAN}Начинаем скачивание {len(episodes_to_download)} эпизодов{Style.RESET_ALL}")
        
        successful_downloads = 0
        failed_downloads = []
        
        for season, episode in episodes_to_download:
            try:
                # Получаем поток для эпизода
                stream = rezka.getStream(season, episode, translation=translator_id)
                if not stream or selected_quality not in stream.videos:
                    failed_downloads.append((season, episode, "Поток недоступен"))
                    continue
                
                video_url = stream.videos[selected_quality][0]
                filename = f"S{season:02d}E{episode:02d}_{selected_quality}.mp4"
                filepath = folder_path / filename
                
                success, message = download_manager.download_file(
                    video_url, str(filepath), f"S{season}E{episode}"
                )
                
                if success:
                    successful_downloads += 1
                else:
                    failed_downloads.append((season, episode, message))
                    
            except Exception as e:
                failed_downloads.append((season, episode, str(e)))
        
        # Отчет о результатах
        print(f"\n{Fore.GREEN}Скачивание завершено!{Style.RESET_ALL}")
        print(f"{Fore.BLUE}Успешно: {successful_downloads}{Style.RESET_ALL}")
        print(f"{Fore.RED}Неудачно: {len(failed_downloads)}{Style.RESET_ALL}")
        
        if failed_downloads:
            print(f"\n{Fore.RED}Неудачные скачивания:{Style.RESET_ALL}")
            for season, episode, error in failed_downloads:
                print(f"{Fore.RED}S{season}E{episode}: {error}{Style.RESET_ALL}")
        
        return successful_downloads > 0
        
    except Exception as e:
        logger.error(f"Ошибка при обработке сериала: {e}")
        return False

def detect_content_type(rezka: HdRezkaApi) -> str:
    """Определение типа контента"""
    try:
        if hasattr(rezka, 'type'):
            if rezka.type == Movie:
                return "movie"
            elif rezka.type == TVSeries:
                return "series"
        
        # Альтернативный способ определения
        if hasattr(rezka, 'seriesInfo') and rezka.seriesInfo:
            return "series"
        elif hasattr(rezka, 'translators') and rezka.translators:
            return "movie"
        
        return "unknown"
        
    except Exception as e:
        logger.error(f"Ошибка определения типа контента: {e}")
        return "unknown"

def main():
    """Главная функция"""
    try:
        # Загружаем конфигурацию
        config = DownloadConfig()
        config.load_config()
        
        # Создаем менеджер скачивания
        download_manager = DownloadManager(config)
        
        while True:
            clear_console()
            print(f"{Fore.CYAN}=== HDRezka Downloader ==={Style.RESET_ALL}")
            print(f"{Fore.GREEN}[1] Настройки{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Или введите ссылку на HDRezka:{Style.RESET_ALL}")
            
            user_input = input(f"{Fore.YELLOW}Ваш выбор: {Style.RESET_ALL}").strip()
            
            if user_input == "1":
                # Открываем меню настроек
                show_settings_menu(config)
                continue
            elif not user_input:
                print(f"{Fore.RED}Ввод не может быть пустым{Style.RESET_ALL}")
                time.sleep(1)
                continue
            
            # Проверяем URL
            parsed_url = urlparse(user_input)
            if not parsed_url.scheme or not parsed_url.netloc:
                print(f"{Fore.RED}Некорректный URL{Style.RESET_ALL}")
                time.sleep(2)
                continue
            
            clear_console()
            
            # Создаем объект API
            print(f"{Fore.CYAN}Подключение к HDRezka...{Style.RESET_ALL}")
            rezka = HdRezkaApi(user_input)
            
            # Проверяем успешность подключения
            if not rezka.ok:
                print(f"{Fore.RED}Ошибка подключения: {rezka.exception}{Style.RESET_ALL}")
                input(f"{Fore.YELLOW}Нажмите Enter для продолжения...{Style.RESET_ALL}")
                continue
            
            # Определяем тип контента
            content_type = detect_content_type(rezka)
            
            if content_type == "unknown":
                print(f"{Fore.RED}Не удалось определить тип контента{Style.RESET_ALL}")
                input(f"{Fore.YELLOW}Нажмите Enter для продолжения...{Style.RESET_ALL}")
                continue
            
            # Получаем название
            content_name = "Unknown"
            if hasattr(rezka, 'name') and rezka.name:
                content_name = rezka.name
            elif hasattr(rezka, 'title') and rezka.title:
                content_name = rezka.title
            
            print(f"{Fore.GREEN}Найден {content_type}: {content_name}{Style.RESET_ALL}")
            
            # Обрабатываем контент
            if content_type == "movie":
                success = process_movie(rezka, config, download_manager, content_name)
            elif content_type == "series":
                success = process_series(rezka, config, download_manager, content_name)
            else:
                success = False
            
            # Показываем статистику
            stats = download_manager.stats
            print(f"\n{Fore.MAGENTA}Статистика скачивания:{Style.RESET_ALL}")
            print(f"{Fore.BLUE}Всего попыток: {stats['total_downloads']}{Style.RESET_ALL}")
            print(f"{Fore.GREEN}Успешно: {stats['successful_downloads']}{Style.RESET_ALL}")
            print(f"{Fore.RED}Неудачно: {stats['failed_downloads']}{Style.RESET_ALL}")
            print(f"{Fore.CYAN}Скачано байт: {stats['total_bytes']:,}{Style.RESET_ALL}")
            
            # Сохраняем конфигурацию
            config.save_config()
            
            if success:
                print(f"\n{Fore.GREEN}Операция завершена успешно!{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}Операция завершена с ошибками{Style.RESET_ALL}")
            
            # Проверяем автоматическую перезагрузку
            auto_reload_functionality(config)
            break
            
    except KeyboardInterrupt:
        print(f"\n{Fore.YELLOW}Операция прервана пользователем{Style.RESET_ALL}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        print(f"{Fore.RED}Произошла критическая ошибка. Проверьте лог-файл.{Style.RESET_ALL}")
        sys.exit(1)

if __name__ == "__main__":
    main()