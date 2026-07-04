from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

import datetime
import re

# 定数設定
TUT_CAMPUSSY_URL = 'https://kyo-web.teu.ac.jp/campussy/'
VIEW_RESULT_COUNT = '200'
WAIT_SECONDS = 30

def _get_current_academic_year() -> int:
    now = datetime.datetime.now()
    current_year = now.year

    # 翌年1~3月の場合は、前年度のデータを取得
    if 1 <= now.month <= 3:
        current_year -= 1

    return current_year

def _select_academic_year(driver: WebDriver, academic_year: int | None) -> bool:
    if academic_year is None:
        return True

    target_year = str(academic_year)
    nendo_elements = driver.find_elements(By.ID, 'nendo')
    if nendo_elements:
        nendo_elements[0].clear()
        nendo_elements[0].send_keys(target_year)
        return True

    excluded_ids = ['jikanwariShozokuCode']
    excluded_names = ['_displayCount']

    for select_element in driver.find_elements(By.TAG_NAME, 'select'):
        select_id = select_element.get_attribute('id') or ''
        select_name = select_element.get_attribute('name') or ''

        if select_id in excluded_ids or select_name in excluded_names:
            continue

        select = Select(select_element)
        for option in select.options:
            option_value = (option.get_attribute('value') or '').strip()
            option_text = option.text.strip().replace(' ', '').replace('\u3000', '')

            if target_year in option_value or target_year in option_text:
                option.click()
                return True

    return False

def _select_department(driver: WebDriver, department_name: str) -> None:
    department_selects = driver.find_elements(By.ID, 'jikanwariShozokuCd')
    if department_selects:
        Select(department_selects[0]).select_by_value(department_name)
        return

    # 旧フォームのid。応用生物学部(BT)は先頭に特殊文字が付く場合がある。
    old_department_select = Select(driver.find_element(By.ID, 'jikanwariShozokuCode'))
    if department_name == "BT":
        try:
            old_department_select.select_by_value("BT")
        except:
            old_department_select.select_by_value("﻿BT")
    else:
        old_department_select.select_by_value(department_name)

def _extract_lecture_code_from_onclick(onclick: str) -> str | None:
    match = re.search(r"/syllabus/\d+/[^/]+/[^/]+?_(?P<code>[^/_]+)_ja_JP\.html", onclick)
    if match:
        return match.group('code')

    match = re.search(r"/syllabus/\d+/[^/]+?_(?P<code>[^/_]+)_ja_JP\.html", onclick)
    if match:
        return match.group('code')

    return None

def _get_lecture_code_list_from_result_buttons(driver: WebDriver) -> list[str]:
    lecture_code_list = []

    for input_element in driver.find_elements(By.CSS_SELECTOR, 'input[onclick*="viewSyllabus"]'):
        lecture_code = _extract_lecture_code_from_onclick(input_element.get_attribute('onclick') or '')
        if lecture_code:
            lecture_code_list.append(lecture_code)

    return lecture_code_list

def _get_next_page_link(driver: WebDriver):
    next_links = driver.find_elements(By.XPATH, '//a[contains(normalize-space(.), "次へ")]')
    return next_links[0] if next_links else None

# 現在のページ数及び全体ページ数を取得する関数
def _get_search_result_page_num(driver: WebDriver) -> dict:
    # 検索結果の件数を表示するエレメントを取得
    search_result_count_element = driver.find_element(By.XPATH, '/html/body/form/div[2]/p[1]').text

    # 検索結果件数のテキスト部分を抽出
    search_result_count_list =  re.findall(r'\全部で .*\あります', search_result_count_element) 

    # 全体ページ数を取得
    search_result_count_all = int(search_result_count_list[0].replace('全部で ', '').replace('件あります', ''))

    # 現在のページ数を取得
    current_page_count_element = driver.find_element(By.XPATH, '/html/body/form/div[2]/p[1]/b[2]').text
    current_page_count = int(current_page_count_element.replace("件目", ''))

    return {
        'current_page_result_count': current_page_count,
        'total_page_result_count': search_result_count_all
    }

def _get_lecture_code_list_from_search_result_element(driver: WebDriver) -> list[str]:
    # 検索結果の件数を取得
    th_tags_elements = driver.find_elements(By.XPATH, '/html/body/form/div[2]/table/tbody/tr')

    # 時間割コードを格納するリスト
    lecture_code_list = []
    for i in enumerate(th_tags_elements):
        lecture_code_list.append(driver.find_element(By.XPATH, f'/html/body/form/div[2]/table/tbody/tr[{str(i[0]+1)}]/td[4]').text)

    return lecture_code_list


# 学外シラバスから時間割コードを取得する関数
# @param: 取得対象の学部名
def get_lecture_code(department_name: str, driver_init: WebDriver, academic_year: int | None = None) -> list[str] | None:
    driver = driver_init()
    wait = WebDriverWait(driver, WAIT_SECONDS)

    try:
        # シラバス検索画面に遷移
        driver.get(TUT_CAMPUSSY_URL)

        if driver.find_elements(By.NAME, "search"):
            # 旧画面用のiframe。現行画面ではiframeは存在しない。
            driver.switch_to.frame(driver.find_element(By.NAME, "search"))

        wait.until(lambda d: d.find_elements(By.ID, 'jikanwariShozokuCd') or d.find_elements(By.ID, 'jikanwariShozokuCode'))

        if not _select_academic_year(driver, academic_year):
            if academic_year != _get_current_academic_year():
                return None

        _select_department(driver, department_name)

        # 一覧表示件数を200件(最大値)に変更
        Select(driver.find_element(By.NAME, '_displayCount')).select_by_value(VIEW_RESULT_COUNT)

        search_buttons = driver.find_elements(By.NAME, '_eventId_search')
        if search_buttons:
            search_buttons[0].click()
        else:
            search_button = driver.find_elements(By.XPATH,'//*[@id = "jikanwariKeywordForm"]/table[2]/tbody/tr/td/table/tbody/tr[9]/td/input[1]')[0]
            search_button.click()

        driver.switch_to.default_content()

        if driver.find_elements(By.NAME, "result"):
            # 旧画面用の検索結果iframe。
            driver.switch_to.frame(driver.find_element(By.NAME, "result"))
            try:
                page_data = _get_search_result_page_num(driver)
            except:
                return None

            lecture_code_list = []
            total_page = (
                page_data['total_page_result_count']
                + page_data['current_page_result_count']
                - 1
            ) // page_data['current_page_result_count']
            
            for page_index in range(0, total_page):
                lecture_code_list.extend(_get_lecture_code_list_from_search_result_element(driver))

                # 次のページがある場合、次ページに遷移
                if page_index < total_page - 1:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(driver.find_element(By.NAME, "result"))
                    driver.find_elements(By.XPATH, '/html/body/form/div[2]/p[1]/a')[-1].click()

            return lecture_code_list

        try:
            wait.until(lambda d: d.title == 'シラバス参照／検索結果' or d.find_elements(By.CSS_SELECTOR, 'input[onclick*="viewSyllabus"]'))
        except TimeoutException:
            return None

        lecture_code_list = []

        while True:
            page_lecture_codes = _get_lecture_code_list_from_result_buttons(driver)
            lecture_code_list.extend(page_lecture_codes)

            next_link = _get_next_page_link(driver)
            if next_link is None:
                break

            previous_page_source = driver.page_source
            next_link.click()
            try:
                wait.until(lambda d: d.page_source != previous_page_source)
            except TimeoutException:
                break

        if not lecture_code_list:
            return None

        return lecture_code_list
    finally:
        driver.quit()
