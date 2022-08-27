import json
import datetime
import calendar
import requests
from bs4 import BeautifulSoup
from firebase_service.cloud import CloudDb


class Desu(CloudDb):
    URL = "https://desu.me/"
    HEADERS = {'User-Agent': 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:96.0) Gecko/20100101 Firefox/96.0'}

    def date_to_iso(self, date):
        months_ru = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

        days = {'Понедельник': 'Monday',
                'Вторник': 'Tuesday',
                'Среда': 'Wednesday',
                'Четверг': ' Thursday',
                'Пятница': 'Friday',
                'Суббота': 'Saturday',
                'Воскресенье': 'Sunday'}

        if len(date.split()) != 1:
            date_elements = date.split()
            if date_elements[0][0] != '0' and 1 <= int(date_elements[0]) < 10:
                day = f'0' + date_elements[0]
            else:
                day = date_elements[0]

            month = months_ru.index(date_elements[1]) + 1
            if 1 <= month < 10:
                month = f'0' + str(month)

            year = date_elements[2]
            result = f'{year}-{month}-{day}'

            return result

        if date == 'Сегодня':
            result = datetime.date.today()
            return str(result)

        elif date == 'Вчера':
            result = datetime.date.today() - datetime.timedelta(1)
            return str(result)

        elif date in days:
            current_date = datetime.date.today()

            for i in range(1, 8):
                release_day = current_date - datetime.timedelta(i)
                if calendar.day_name[release_day.weekday()] == days.get(date):
                    return str(release_day)

    def request(self, link='', params=None):
        if self.URL in link:
            html = requests.get(link, headers=self.HEADERS, params=params)
            return html
        else:
            html = requests.get(self.URL + link, headers=self.HEADERS, params=params)
            return html

    def get_content(self, link='', params=None):
        html = self.request(link, params)
        if html.status_code == 200:
            soup = BeautifulSoup(html.text, 'html.parser')
            return soup

    def get_manga(self, manga_url):
        print(f'getting {manga_url}')
        content = self.get_content(manga_url)
        info = content.select('div.mainContent')
        manga_chapters = content.select('.chlist li')
        chapters = []

        # titles parsing
        titles = []
        for i in info:
            original_title = i.find('div', {'class': 'titleBar'}).find('span', {'class': 'name'}).get_text()
            ru_title = i.find('div', {'class': 'titleBar'}).find('span', {'class': 'rus-name'}).get_text()

            try:
                other_titles = i.find('span', {'class': 'alternativeHeadline'}).get_text().split(',')

                for name in other_titles:
                    edited_name = ' '.join(name.split())
                    other_titles[other_titles.index(name)] = edited_name

            except AttributeError:
                other_titles = []

            titles.append(original_title)
            titles.append(ru_title)
            titles = titles + other_titles

            title_type = i.find('div', {'class': 'line-container'}).find('div', {'class': 'value'}).get_text()

            genres = [j.get_text() for j in i.find('ul', {'class': 'tagList'}).find_all('a')]

            manga_status = True if i.find('span', {'class': 'b-anime_status_tag'}).get_text() == 'издано' else False

            manga_year = (i.find('span', {'class': 'b-anime_status_tag'}).find_parent().get_text()).split()

            for char in manga_year:
                if len(char) == 4 and char.isnumeric():
                    year = int(char)
                    break
                elif i.find('span', {'class': 'b-anime_status_tag'}).get_text() == 'Закрыт правообладателем':
                    year = ''
                    break

            description = " ".join(i.find('div', {'class': 'prgrph'}).get_text().split())

            rating = i.find('div', {'class': 'score-value'}).get_text() + '/10'

            img = self.URL + i.find('div', {'class': 'c-poster'}).find('img').get('src')[1::]

            manga_content = {
                "titles": titles,
                "type": title_type,
                "rating": rating,
                "img": img,
                "genres": genres,
                "year": year,
                "manga_сompleted": manga_status,
                "description": description,
                "chapters": {}
            }

        # getting chapter list
        for chapter in manga_chapters:
            # print(manga_chapters)
            chapter_name = chapter.find('a').get_text()
            chapter_url = chapter.find('a').get('href')
            release_date = self.date_to_iso(chapter.find('span', {'class': 'date'}).get_text()[:-8])
            chapters.append(chapter_name)

            chapter_info = {
                "chapter_name": chapter_name,
                "chapter_url": self.URL + chapter_url,
                "release_date": release_date,
                "images_urls": self.reader(chapter_url),
            }

            chapters.append(chapter_info)

            manga_content.update({"chapters": chapters})

        return manga_content

    def reader(self, link):
        from .script_parser import script_parser

        content = self.get_content(link)
        reader = content.find('head')
        script = str(reader.find_all_next('script', type="text/javascript")[-3])
        script_array = script.split()
        result = script_parser(script_array)

        return result

    def get_popular(self, page=1):
        # https: // desu.me / manga /?order_by = popular  24 per page
        items = self.get_content(f'https://desu.me/manga/?order_by=popular&page={page}')
        content = items.select('div.animeList ol li')

        manga_data = {

        }

        data_list = []
        title_counter = 0
        for i in content:
            href = i.find('a').get('href')
            title = i.find('h3').get_text()
            picture = i.find('span', {'class': 'img'}).get('style').split()[1]
            ulr = picture.replace("url('/", '')
            picture_ulr = self.URL + ulr.replace("')", '')

            data = {
                'href': href,
                'title': title,
                'picture_url': picture_ulr
            }

            data_list.append(data)

            manga = self.get_manga(href)

            title_counter += 1

            manga_data.update({title: manga})

            self.add_popular(language='ru', source='desu', data=manga_data)

            if title_counter == 24:
                page += 1
                self.get_popular(page)

        # making json

        result = json.dumps(manga_data, sort_keys=False, indent=4, separators=(',', ': '), ensure_ascii=False)
        # print(result)
        with open('desu/catalogue.json', 'w', encoding='utf-8') as file:
            file.write(result)
        return result
