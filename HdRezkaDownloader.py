import os
import requests
from HdRezkaApi import HdRezkaApi
from HdRezkaApi.types import TVSeries
from tqdm import tqdm
from colorama import init, Fore, Style

# Инициализация colorama
init()

def clear_console():
    """Очищает консоль"""
    os.system('cls' if os.name == 'nt' else 'clear')

def get_user_choice(prompt, max_value):
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

def download_episode(rezka, season_num, episode_num, translator_id, quality, folder_path, series_title):
    """Скачивает одну серию"""
    try:
        stream = rezka.getStream(season_num, episode_num, translation=translator_id)
        if not stream or not hasattr(stream, 'videos'):
            return False, f"Серия недоступна"
        
        if quality not in stream.videos:
            return False, f"Качество '{quality}' недоступно"
        
        url_to_download = stream.videos[quality][0]
        filename = f"S{season_num}E{episode_num}_{quality}.mp4"
        filepath = os.path.join(folder_path, filename)
        
        print(f"{Fore.CYAN}Скачивание {series_title}: {filename}{Style.RESET_ALL}")
        response = requests.get(url_to_download, stream=True)
        total = int(response.headers.get('content-length', 0))
        
        with open(filepath, 'wb') as f, tqdm(
            desc=filename,
            total=total,
            unit='B',
            unit_scale=True,
            unit_divisor=1024,
            colour='green'
        ) as bar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    bar.update(len(chunk))
        return True, "Успешно"
    except Exception as e:
        return False, str(e)

def process_single_part(url, part_name):
    """Обрабатывает одну часть сериала"""
    rezka = HdRezkaApi(url)
    
    # Собираем информацию о всех сезонах и сериях
    combined_seasons = {}
    for translator_id, data in rezka.seriesInfo.items():
        episodes_by_season = data.get('episodes', {})
        for season_num, episodes in episodes_by_season.items():
            if season_num not in combined_seasons:
                combined_seasons[season_num] = set(episodes.keys())
            else:
                combined_seasons[season_num].update(episodes.keys())
    
    # Преобразуем в отсортированные списки
    for season in combined_seasons:
        combined_seasons[season] = sorted(combined_seasons[season])
    
    # Показываем доступные сезоны
    print(f"{Fore.MAGENTA}Список сезонов и серий для '{part_name}':{Style.RESET_ALL}")
    print(f"{Fore.GREEN}[0] Все серии{Style.RESET_ALL}")
    sorted_seasons = sorted(combined_seasons.keys())
    for i, season in enumerate(sorted_seasons, 1):
        print(f"{Fore.GREEN}[{i}] Сезон {season}: {len(combined_seasons[season])} серий{Style.RESET_ALL}")
    
    # Выбор сезона
    season_choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер сезона: {Style.RESET_ALL}", len(sorted_seasons))
    clear_console()
    
    # Определяем что скачивать
    if season_choice == 0:
        # Скачиваем все сезоны
        download_mode = "all_seasons"
        target_seasons = sorted_seasons
        target_episodes = None
    else:
        # Выбран конкретный сезон
        selected_season = sorted_seasons[season_choice - 1]
        episodes_in_season = combined_seasons[selected_season]
        
        print(f"{Fore.MAGENTA}Серии в сезоне {selected_season}:{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[0] Все серии{Style.RESET_ALL}")
        for i, ep in enumerate(episodes_in_season, 1):
            print(f"{Fore.GREEN}[{i}] Серия {ep}{Style.RESET_ALL}")
        
        episode_choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер серии: {Style.RESET_ALL}", len(episodes_in_season))
        clear_console()
        
        if episode_choice == 0:
            # Скачиваем весь сезон
            download_mode = "whole_season"
            target_seasons = [selected_season]
            target_episodes = episodes_in_season
        else:
            # Скачиваем одну серию
            download_mode = "single_episode"
            target_seasons = [selected_season]
            target_episodes = [episodes_in_season[episode_choice - 1]]
    
    # Находим подходящие переводы
    valid_translators = {}
    for tid, data in rezka.seriesInfo.items():
        translator_episodes = data.get("episodes", {})
        
        # Проверяем, есть ли у переводчика нужные серии
        has_all_needed = True
        for season_num in target_seasons:
            if season_num not in translator_episodes:
                has_all_needed = False
                break
            
            if download_mode == "single_episode":
                if target_episodes[0] not in translator_episodes[season_num]:
                    has_all_needed = False
                    break
            elif download_mode == "whole_season":
                season_episodes = set(translator_episodes[season_num].keys())
                needed_episodes = set(target_episodes)
                if not needed_episodes.issubset(season_episodes):
                    has_all_needed = False
                    break
        
        if has_all_needed:
            valid_translators[tid] = data
    
    if not valid_translators:
        print(f"{Fore.RED}Нет подходящих переводов для выбранных серий{Style.RESET_ALL}")
        return
    
    # Выбор перевода
    if len(valid_translators) == 1:
        translator_id = list(valid_translators.keys())[0]
        translator_name = valid_translators[translator_id].get("translator_name", "Без названия")
        print(f"{Fore.BLUE}Автоматически выбран перевод: {translator_name}{Style.RESET_ALL}")
    else:
        print(f"{Fore.MAGENTA}Доступные озвучки:{Style.RESET_ALL}")
        translator_list = list(valid_translators.items())
        for i, (tid, translator) in enumerate(translator_list, 1):
            name = translator.get("translator_name", "Без названия")
            premium_status = " (Премиум)" if translator.get("premium") else ""
            print(f"{Fore.GREEN}[{i}] {name}{premium_status}{Style.RESET_ALL}")
        
        translator_choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер озвучки: {Style.RESET_ALL}", len(translator_list))
        translator_id = translator_list[translator_choice - 1][0]
        clear_console()
    
    # Устанавливаем переводчика
    rezka.translator = int(translator_id)
    
    # Получаем тестовый поток для выбора качества
    test_season = target_seasons[0]
    if download_mode == "single_episode":
        test_episode = target_episodes[0]
    else:
        test_episode = combined_seasons[test_season][0]
    
    test_stream = rezka.getStream(test_season, test_episode, translation=translator_id)
    if not test_stream or not hasattr(test_stream, 'videos'):
        print(f"{Fore.RED}Не удалось получить поток для тестирования{Style.RESET_ALL}")
        return
    
    # Выбор качества
    qualities = list(test_stream.videos.keys())
    if not qualities:
        print(f"{Fore.RED}Нет доступных качеств{Style.RESET_ALL}")
        return
    
    print(f"{Fore.MAGENTA}Выберите качество:{Style.RESET_ALL}")
    for i, quality in enumerate(qualities, 1):
        print(f"{Fore.GREEN}[{i}] {quality}{Style.RESET_ALL}")
    
    quality_choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер качества: {Style.RESET_ALL}", len(qualities))
    selected_quality = qualities[quality_choice - 1]
    clear_console()
    
    # Создаем папку для скачивания
    title = part_name.replace('/', '-').strip()
    folder_path = os.path.join("Videos", title)
    os.makedirs(folder_path, exist_ok=True)
    
    # Скачиваем серии с возможностью повторного скачивания
    download_episodes_with_retry(rezka, combined_seasons, download_mode, target_seasons, target_episodes, 
                                translator_id, selected_quality, folder_path, title)

def download_episodes_with_retry(rezka, combined_seasons, download_mode, target_seasons, target_episodes, 
                                translator_id, selected_quality, folder_path, title):
    """Скачивает серии с возможностью повторного скачивания неудачных попыток"""
    
    # Определяем список серий для скачивания
    episodes_to_download = []
    
    if download_mode == "all_seasons":
        # Скачиваем все сезоны
        for season_num in target_seasons:
            episodes_list = combined_seasons[season_num]
            for episode_num in episodes_list:
                episodes_to_download.append((season_num, episode_num))
    
    elif download_mode == "whole_season":
        # Скачиваем весь сезон
        season_num = target_seasons[0]
        for episode_num in target_episodes:
            episodes_to_download.append((season_num, episode_num))
    
    elif download_mode == "single_episode":
        # Скачиваем одну серию
        season_num = target_seasons[0]
        episode_num = target_episodes[0]
        episodes_to_download.append((season_num, episode_num))
    
    # Основной цикл скачивания с повторными попытками
    total_downloaded = 0
    failed_episodes = []
    
    # Первая попытка скачивания
    for season_num, episode_num in episodes_to_download:
        success, error_msg = download_episode(rezka, season_num, episode_num, translator_id, selected_quality, folder_path, title)
        if success:
            total_downloaded += 1
        else:
            failed_episodes.append((season_num, episode_num, error_msg))
    
    # Цикл повторных попыток
    attempt_count = 1
    while failed_episodes:
        print(f"\n{Fore.GREEN}Скачивание завершено! (Попытка {attempt_count}){Style.RESET_ALL}")
        print(f"{Fore.BLUE}Скачано: {total_downloaded}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}Ошибок: {len(failed_episodes)}{Style.RESET_ALL}")
        
        # Показываем список неудачных загрузок
        print(f"\n{Fore.RED}Не удалось скачать:{Style.RESET_ALL}")
        for i, (season, episode, error) in enumerate(failed_episodes, 1):
            print(f"{Fore.RED}[{i}] S{season} E{episode} {title} ({error}){Style.RESET_ALL}")
        
        # Предлагаем повторить скачивание
        print(f"\n{Fore.MAGENTA}Варианты действий:{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[1] Повторить скачивание неудачных серий{Style.RESET_ALL}")
        print(f"{Fore.GREEN}[2] Завершить{Style.RESET_ALL}")
        
        retry_choice = get_user_choice(f"\n{Fore.YELLOW}Выберите действие: {Style.RESET_ALL}", 2)
        
        if retry_choice == 2:
            break
        
        clear_console()
        print(f"{Fore.CYAN}Повторное скачивание неудачных серий...{Style.RESET_ALL}\n")
        
        # Сохраняем текущий список неудачных серий
        current_failed = failed_episodes.copy()
        failed_episodes = []
        
        # Пытаемся скачать неудачные серии
        for season_num, episode_num, _ in current_failed:
            success, error_msg = download_episode(rezka, season_num, episode_num, translator_id, selected_quality, folder_path, title)
            if success:
                total_downloaded += 1
            else:
                failed_episodes.append((season_num, episode_num, error_msg))
        
        attempt_count += 1
    
    # Финальный отчет
    print(f"\n{Fore.GREEN}Финальный результат:{Style.RESET_ALL}")
    print(f"{Fore.BLUE}Общее количество скачанных серий: {total_downloaded}{Style.RESET_ALL}")
    
    if failed_episodes:
        print(f"{Fore.RED}Серии, которые так и не удалось скачать:{Style.RESET_ALL}")
        for i, (season, episode, error) in enumerate(failed_episodes, 1):
            print(f"{Fore.RED}[{i}] S{season} E{episode} {title} ({error}){Style.RESET_ALL}")
    else:
        print(f"{Fore.GREEN}Все серии успешно скачаны!{Style.RESET_ALL}")

def main():
    # Получаем URL сериала
    url = input(f"{Fore.YELLOW}Введите ссылку на сериал: {Style.RESET_ALL}")
    clear_console()
    
    rezka = HdRezkaApi(url)
    
    # Выбор части сериала
    if rezka.otherParts:
        print(f"{Fore.MAGENTA}Список частей:{Style.RESET_ALL}")
        all_parts = [{"Все части": url}] + list(reversed(rezka.otherParts))
        for i, part in enumerate(all_parts):
            for name in part:
                print(f"{Fore.GREEN}[{i}] {name}{Style.RESET_ALL}")
        choice = get_user_choice(f"\n{Fore.YELLOW}Введите номер нужной части: {Style.RESET_ALL}", len(all_parts) - 1)
        clear_console()
    else:
        all_parts = [{"Все части": url}]
        choice = 0
    
    # Если выбрано "Все части", скачиваем все части
    if choice == 0 and rezka.otherParts:
        # Скачиваем все части
        for part_index, part in enumerate(all_parts[1:], 1):  # Пропускаем "Все части"
            part_name = list(part.keys())[0]
            part_url = list(part.values())[0]
            
            print(f"{Fore.CYAN}Обрабатываем часть: {part_name}{Style.RESET_ALL}")
            process_single_part(part_url, part_name)
            print(f"{Fore.GREEN}Часть '{part_name}' завершена!{Style.RESET_ALL}\n")
    else:
        # Обрабатываем выбранную часть
        selected_part = all_parts[choice]
        part_name = list(selected_part.keys())[0]
        selected_url = list(selected_part.values())[0]
        
        if part_name == "Все части":
            # Получаем реальное название сериала
            try:
                if hasattr(rezka, 'name') and rezka.name:
                    part_name = rezka.name
                else:
                    part_name = url.split('/')[-1].split('-')[0].replace('.html', '')
            except:
                part_name = "Unknown_Series"
        
        process_single_part(selected_url, part_name)

if __name__ == "__main__":
    main()