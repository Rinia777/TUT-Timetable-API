import ssl
from bs4 import BeautifulSoup
import requests
import datetime
import re
import urllib3

TUT_SYLLABUS_URL = 'https://kyo-web.teu.ac.jp/syllabus'
REQUEST_TIMEOUT_SECONDS = 15
DEPARTMENT_FALLBACKS = {
    'ES': ['ES', 'ESE5', 'ESE6', 'ESE7'],
    'HS': ['HS', 'HSH1', 'HSH2', 'HSH3', 'HSH4', 'HSH5', 'HSH6'],
}

class _CustomHttpAdapter (requests.adapters.HTTPAdapter):
    def __init__(self, ssl_context=None, **kwargs):
        self.ssl_context = ssl_context
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False):
        self.poolmanager = urllib3.poolmanager.PoolManager(
            num_pools=connections, maxsize=maxsize,
            block=block, ssl_context=self.ssl_context)

def _fetch_syllabus(current_year: int, department_name: str, lecture_code: str):
    session = requests.session()
    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    ctx.options |= 0x4
    session.mount('https://', _CustomHttpAdapter(ctx))

    departments = DEPARTMENT_FALLBACKS.get(department_name, [department_name])
    urls = []
    for department in departments:
        urls.append(f'{TUT_SYLLABUS_URL}/{current_year}/{department}/{department}_{lecture_code}_ja_JP.html')
        urls.append(f'{TUT_SYLLABUS_URL}/{current_year}/{department}_{lecture_code}_ja_JP.html')

    last_response = None
    for url in urls:
        try:
            res = session.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        except requests.RequestException:
            continue

        if res.status_code != 404:
            return res
        last_response = res

    return last_response

def get_current_academic_year() -> int:
    now = datetime.datetime.now()
    current_year = now.year

    # 翌年1~3月の場合は、前年度のデータを取得
    if 1 <= now.month <= 3:
        current_year -= 1

    return current_year

def _format_string(text: str) -> str:
    return text.strip().replace(' ', '').replace(
    '\r\n', '').replace('\u3000', '').replace('\n', '').replace('\r', '').replace('\t', '').replace(u'\xa0', u'')

def _format_key(text: str) -> str:
    return _format_string(text).replace('／', '').replace('/', '').replace('・', '').replace('（', '(').replace('）', ')')

def _extract_table_data(lecture_information) -> dict:
    table_data = {}

    for tr in lecture_information.find_all('tr'):
        th_data = tr.find_all('th')
        td_data = tr.find_all('td')

        if len(th_data) == 1 and len(td_data) >= 1:
            table_data[_format_key(th_data[0].text)] = _format_string(td_data[0].text)

    return table_data

def _get_table_value(table_data: dict, tags: list[str]) -> str:
    for tag in tags:
        value = table_data.get(_format_key(tag))
        if value:
            return value

    return ''

def _split_list(text: str) -> list[str]:
    if not text:
        return []

    return [item for item in text.split(',') if item]

def _parse_number_of_credits(text: str) -> int:
    if not text:
        return 0

    return int(float(text))

def _extract_lecturers(tables: list) -> list[str]:
    for table in tables:
        header_tags = [_format_key(th.text) for th in table.find_all('th')]
        if '教員名' not in header_tags:
            continue

        lecturers = []
        for tr in table.find_all('tr'):
            td_data = tr.find_all('td')
            if td_data:
                lecturer = _format_string(td_data[0].text)
                if lecturer:
                    lecturers.append(lecturer)

        if lecturers:
            return lecturers

    return []

def _extract_update_at(bs: BeautifulSoup) -> str:
    match = re.search(r'(\d{4}/\d{1,2}/\d{1,2})現在', _format_string(bs.get_text()))
    return match.group(1) if match else ''

def _find_table_data(table_data_list: list[dict], required_tags: list[str]) -> dict:
    normalized_required_tags = [_format_key(tag) for tag in required_tags]

    for table_data in table_data_list:
        if any(tag in table_data for tag in normalized_required_tags):
            return table_data

    return {}

# ===========================================================================
# 講義データ取得関数 (時間割コード => 授業内容等(単位数))
# ===========================================================================
def get_timetable(department_name: str, lecture_code : str, academic_year: int | None = None) -> dict:
    target_year = academic_year if academic_year is not None else get_current_academic_year()
    res = _fetch_syllabus(target_year, department_name, lecture_code)

    if res is None or res.status_code == 404:
        return None

    bs = BeautifulSoup(res.content, 'html.parser')

    # 講義情報が存在しない場合
    if not bs.find_all('table', class_='syllabus-normal'):
        return None

    tables = bs.find_all('table', class_='syllabus-normal')
    table_data_list = [_extract_table_data(table) for table in tables]

    basic_data = _find_table_data(table_data_list, ['科目名'])
    details_data = _find_table_data(table_data_list, ['授業概要'])
    update_at_text = _extract_update_at(bs)

    lecturers = _extract_lecturers(tables)
    if not lecturers:
        lecturers = _split_list(_get_table_value(basic_data, ['担当教員（所属）']))

    # dictに変換
    lecture_data = {
        'lectureCode': lecture_code,
        'courseName': _get_table_value(basic_data, ['科目名']),
        'lecturer': lecturers,
        'regularOrIntensive': _get_table_value(basic_data, ['授業科目区分']),
        'courseType': _get_table_value(basic_data, ['授業種別']),
        'courseStart': _get_table_value(basic_data, ['開講学期']),
        'classPeriod': _split_list(_get_table_value(basic_data, ['開講曜限'])),
        'targetDepartment': _get_table_value(basic_data, ['対象所属']),
        'targetGrade': _split_list(_get_table_value(basic_data, ['対象学年'])),
        'numberOfCredits': _parse_number_of_credits(_get_table_value(basic_data, ['単位数'])),
        'classroom': _split_list(_get_table_value(basic_data, ['教室'])),
        'courceDetails': {
            'courseOverview': _get_table_value(details_data, ['授業概要']),
            'outcomesMeasuredBy': _get_table_value(details_data, ['到達目標']),
            'learningOutcomes': _get_table_value(details_data, ['ラーニング・アウトカムズ(学修到達目標)', 'ラーニングアウトカムズ（学修到達目標）']),
            'teachingMethod': _get_table_value(details_data, ['授業方法']),
            'notices': _get_table_value(details_data, ['履修上の注意']),
            'preparatoryStudy': _get_table_value(details_data, ['準備学習']),
            'gradingGuidelines': _get_table_value(details_data, ['成績評価方法・基準']),
            'textbook': _get_table_value(details_data, ['教科書']),
            'referenceMaterials': _get_table_value(details_data, ['参考書']),
            'courseSchedule': _get_table_value(details_data, ['授業計画']),
            'courseDataUpdatedAt': _get_table_value(details_data, ['更新日']) or update_at_text
        },
        'updateAt': update_at_text
    }

    return lecture_data
