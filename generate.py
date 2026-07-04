import ujson
import os
import argparse
import hashlib
import re
import shutil
from selenium import webdriver
import tqdm

from src import get_lecture_code, get_timetable

try:
    from get_chrome_driver import GetChromeDriver
except ImportError:
    GetChromeDriver = None

DEPARTMENT = ["BT", "CS", "MS", "ES", "ESE5", "ESE6", "ESE7", "X1", "DS", "HS", "HSH1", "HSH2", "HSH3", "HSH4", "HSH5", "HSH6", "X3", "GF", "GH"]

API_ROOT = "docs/api/v1"
ARCHIVE_ROOT = f"{API_ROOT}/archive"
LECTURE_CODES_FILE = "output/lecture_codes.json"
LECTURE_CODES_BY_YEAR_FILE = "output/lecture_codes_by_year.json"
SEARCH_INDEX_DIRECTORY = "search-index"
MAX_ARCHIVE_AGE_YEARS = 2

WEEKDAY_KEYS = {
    "月": "mon",
    "火": "tue",
    "水": "wed",
    "木": "thu",
    "金": "fri",
    "土": "sat",
    "日": "sun",
    "他": "other",
}
WEEKDAY_LABELS = {
    "mon": "月",
    "tue": "火",
    "wed": "水",
    "thu": "木",
    "fri": "金",
    "sat": "土",
    "sun": "日",
    "other": "他",
}
def _driver_init():
    if GetChromeDriver is not None:
        get_driver = GetChromeDriver()
        get_driver.install()

    options = webdriver.ChromeOptions()
    options.add_argument('--headless=new')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-gpu')
    options.add_argument('--disable-dev-shm-usage')
    return webdriver.Chrome(options=options)

def _get_current_academic_year() -> int:
    return get_timetable.get_current_academic_year()

def _get_retained_academic_years() -> list[int]:
    current_year = _get_current_academic_year()
    return [current_year - offset for offset in range(MAX_ARCHIVE_AGE_YEARS + 1)]

def _validate_requested_year(requested_year: int | None) -> None:
    if requested_year is None:
        return

    retained_years = _get_retained_academic_years()
    if requested_year in retained_years:
        return

    retained_years_text = ", ".join(str(year) for year in retained_years)
    raise ValueError(f"Only retained academic years can be fetched: {retained_years_text}")

def _load_json(file_path: str, default):
    if not os.path.exists(file_path):
        return default

    with open(file_path, 'r') as f:
        return ujson.load(f)

def _dump_json(file_path: str, data) -> None:
    directory = os.path.dirname(file_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(file_path, 'w') as f:
        ujson.dump(data, f, ensure_ascii=False, indent=4, encode_html_chars=True)

def _load_lecture_codes_by_year() -> dict:
    lecture_codes_by_year = _load_json(LECTURE_CODES_BY_YEAR_FILE, {})

    if lecture_codes_by_year:
        return lecture_codes_by_year

    legacy_lecture_codes = _load_json(LECTURE_CODES_FILE, None)
    if legacy_lecture_codes is None:
        return {}

    current_year = _get_current_academic_year()
    return {str(current_year): legacy_lecture_codes}

def _get_lecture_code_target_years(requested_year: int | None = None) -> list[int]:
    _validate_requested_year(requested_year)
    if requested_year is not None:
        return [requested_year]

    return _get_retained_academic_years()

def _get_lecture_data_target_years(department: str, requested_year: int | None = None) -> list[int]:
    _validate_requested_year(requested_year)
    if requested_year is not None:
        return [requested_year]

    return _get_retained_academic_years()

def _cleanup_expired_archive_data(lecture_codes_by_year: dict) -> bool:
    retained_years = set(_get_retained_academic_years())
    changed = False

    for academic_year in sorted(_get_archive_years()):
        if academic_year in retained_years:
            continue

        archive_path = f"{ARCHIVE_ROOT}/{academic_year}"
        print(f"Delete expired archive data: {archive_path}")
        shutil.rmtree(archive_path)
        changed = True

    for year_key in sorted(list(lecture_codes_by_year.keys()), key=lambda key: int(key)):
        if int(year_key) in retained_years:
            continue

        print(f"Delete expired lecture codes: {year_key}")
        lecture_codes_by_year.pop(year_key)
        changed = True

    return changed

def _write_lecture_data(lecture_data: dict, lecture_code: str, academic_year: int) -> None:
    current_year = _get_current_academic_year()

    archive_all_path = f"{ARCHIVE_ROOT}/{academic_year}/all/{lecture_code}.json"
    _dump_json(archive_all_path, lecture_data)

    if academic_year != current_year:
        return

    latest_all_path = f"{API_ROOT}/all/{lecture_code}.json"
    _dump_json(latest_all_path, lecture_data)

def _as_list(value) -> list:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]

def _get_schedule_keys(class_periods: list) -> tuple[set[str], set[str], set[str]]:
    weekdays = set()
    periods = set()
    class_period_keys = set()

    for class_period in class_periods:
        if class_period is None:
            continue

        matches = re.findall(r"(他|[月火水木金土日])(\d*)", str(class_period))
        for day_label, period in matches:
            weekday_key = WEEKDAY_KEYS[day_label]
            weekdays.add(weekday_key)

            if period:
                periods.add(period)
                class_period_keys.add(f"{weekday_key}-{period}")
            elif weekday_key == "other":
                periods.add("other")
                class_period_keys.add("other")

    return weekdays, periods, class_period_keys

def _get_regular_or_intensive_id(value: str) -> str:
    return _get_hashed_id(value)

def _get_hashed_id(value: str) -> str:
    if not value:
        return "unknown"

    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]

def _get_course_start_id(value: str) -> str:
    if not value:
        return "unknown"

    match = re.fullmatch(r"(\d{4})年度(.+)", value)
    if match is None:
        return _get_hashed_id(value)

    year, term = match.groups()
    term_keys = {
        "前期": "first",
        "後期": "second",
        "通年": "full",
    }
    term_key = term_keys.get(term)
    if term_key is None:
        return _get_hashed_id(value)

    return f"{year}-{term_key}"

def _get_target_grade_id(value: str) -> str:
    if not value:
        return "unknown"

    normalized_value = value.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    match = re.fullmatch(r"(\d+)年", normalized_value)
    if match is None:
        return _get_hashed_id(value)

    return match.group(1)

def _get_filter_keys(lecture_data: dict) -> dict:
    weekdays, periods, class_periods = _get_schedule_keys(_as_list(lecture_data.get("classPeriod")))
    regular_or_intensive = lecture_data.get("regularOrIntensive") or ""
    course_start = lecture_data.get("courseStart") or ""
    course_type = lecture_data.get("courseType") or ""

    return {
        "weekdayKeys": sorted(weekdays),
        "periodKeys": sorted(periods, key=lambda key: int(key) if key.isdigit() else 9999),
        "classPeriodKeys": sorted(class_periods),
        "regularOrIntensiveKey": _get_regular_or_intensive_id(regular_or_intensive),
        "lecturerKeys": [
            _get_hashed_id(str(lecturer or ""))
            for lecturer in _as_list(lecture_data.get("lecturer"))
        ],
        "courseStartKey": _get_course_start_id(course_start),
        "targetGradeKeys": [
            _get_target_grade_id(str(target_grade or ""))
            for target_grade in _as_list(lecture_data.get("targetGrade"))
        ],
        "courseTypeKey": _get_hashed_id(course_type),
    }

def _get_search_index_entry(lecture_data: dict, api_prefix: str, lecture_code: str) -> dict:
    entry = {
        "lectureCode": lecture_data.get("lectureCode") or lecture_code,
        "courseName": lecture_data.get("courseName"),
        "lecturer": lecture_data.get("lecturer"),
        "regularOrIntensive": lecture_data.get("regularOrIntensive"),
        "courseType": lecture_data.get("courseType"),
        "courseStart": lecture_data.get("courseStart"),
        "classPeriod": lecture_data.get("classPeriod"),
        "targetDepartment": lecture_data.get("targetDepartment"),
        "targetGrade": lecture_data.get("targetGrade"),
        "numberOfCredits": lecture_data.get("numberOfCredits"),
        "classroom": lecture_data.get("classroom"),
        "updateAt": lecture_data.get("updateAt"),
        "path": f"{api_prefix}/all/{lecture_code}.json",
    }
    entry.update(_get_filter_keys(lecture_data))
    return entry

def _increment_filter_count(filters: dict, category: str, key: str, label: str) -> None:
    if not key:
        key = "unknown"

    category_filters = filters.setdefault(category, {})
    item = category_filters.setdefault(key, {
        "key": key,
        "label": label,
        "count": 0,
    })
    item["count"] += 1

def _build_search_filter_metadata(lectures: list[dict]) -> dict:
    filters = {}

    for lecture in lectures:
        for weekday_key in lecture.get("weekdayKeys") or []:
            _increment_filter_count(filters, "weekday", weekday_key, WEEKDAY_LABELS.get(weekday_key, weekday_key))

        for period_key in lecture.get("periodKeys") or []:
            _increment_filter_count(filters, "period", period_key, "他" if period_key == "other" else period_key)

        for class_period_key in lecture.get("classPeriodKeys") or []:
            if class_period_key == "other":
                class_period_label = "他"
            else:
                weekday_key, period_key = class_period_key.split("-", 1)
                class_period_label = f"{WEEKDAY_LABELS.get(weekday_key, weekday_key)}{period_key}"
            _increment_filter_count(filters, "classPeriod", class_period_key, class_period_label)

        regular_or_intensive = lecture.get("regularOrIntensive") or ""
        _increment_filter_count(
            filters,
            "regularOrIntensive",
            lecture.get("regularOrIntensiveKey"),
            regular_or_intensive,
        )

        for lecturer, lecturer_key in zip(
            _as_list(lecture.get("lecturer")),
            lecture.get("lecturerKeys") or [],
        ):
            _increment_filter_count(filters, "lecturer", lecturer_key, str(lecturer or ""))

        course_start = lecture.get("courseStart") or ""
        _increment_filter_count(filters, "courseStart", lecture.get("courseStartKey"), course_start)

        for target_grade, target_grade_key in zip(
            _as_list(lecture.get("targetGrade")),
            lecture.get("targetGradeKeys") or [],
        ):
            _increment_filter_count(filters, "targetGrade", target_grade_key, str(target_grade or ""))

        course_type = lecture.get("courseType") or ""
        _increment_filter_count(filters, "courseType", lecture.get("courseTypeKey"), course_type)

    weekday_order = {key: index for index, key in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun", "other"])}

    def filter_sort_key(category: str, item: dict):
        key = item["key"]
        label = item["label"] or ""

        if category == "weekday":
            return (weekday_order.get(key, 9999), label, key)

        if category in {"period", "targetGrade"}:
            return (int(key) if key.isdigit() else 9999, label, key)

        if category == "classPeriod":
            if key == "other":
                return (9999, 9999, label, key)

            weekday_key, period_key = key.split("-", 1)
            return (
                weekday_order.get(weekday_key, 9999),
                int(period_key) if period_key.isdigit() else 9999,
                label,
                key,
            )

        return (label, key)

    metadata = {}
    for category, values in filters.items():
        metadata[category] = sorted(
            values.values(),
            key=lambda item: filter_sort_key(category, item),
        )

    return metadata

def _build_search_indexes_for_base(base_path: str, api_prefix: str, lecture_codes: dict) -> bool:
    all_directory = f"{base_path}/all"
    if not os.path.isdir(all_directory):
        print(f"Skip search indexes: {all_directory} is not found.")
        return False

    search_index_root = f"{base_path}/{SEARCH_INDEX_DIRECTORY}"
    if os.path.isdir(search_index_root):
        shutil.rmtree(search_index_root)

    built_count = 0
    for department in DEPARTMENT:
        department_lecture_codes = lecture_codes.get(department)
        if department_lecture_codes is None:
            continue

        lectures = []
        for lecture_code in sorted(set(department_lecture_codes)):
            lecture_data = _load_json(f"{all_directory}/{lecture_code}.json", None)
            if lecture_data is None:
                continue

            lectures.append(_get_search_index_entry(lecture_data, api_prefix, lecture_code))

        lectures.sort(key=lambda lecture: (
            str(lecture.get("courseName") or ""),
            str(lecture.get("path") or ""),
        ))
        _dump_json(
            f"{search_index_root}/{department}.json",
            {
                "department": department,
                "count": len(lectures),
                "filters": _build_search_filter_metadata(lectures),
                "lectures": lectures,
            }
        )
        built_count += 1

    print(f"Built search indexes: {api_prefix} ({built_count} departments)")
    return built_count > 0

def _get_archive_years() -> list[int]:
    if not os.path.isdir(ARCHIVE_ROOT):
        return []

    return sorted(
        int(file_name)
        for file_name in os.listdir(ARCHIVE_ROOT)
        if file_name.isdigit() and os.path.isdir(f"{ARCHIVE_ROOT}/{file_name}")
    )

def _build_indexes(requested_year: int | None = None) -> None:
    _validate_requested_year(requested_year)
    lecture_codes_by_year = _load_lecture_codes_by_year()
    if _cleanup_expired_archive_data(lecture_codes_by_year):
        _dump_json(LECTURE_CODES_BY_YEAR_FILE, lecture_codes_by_year)

    if requested_year is None:
        current_year = _get_current_academic_year()
        _build_search_indexes_for_base(
            API_ROOT,
            "/api/v1",
            lecture_codes_by_year.get(str(current_year), {}),
        )
        target_years = _get_archive_years()
    else:
        target_years = [requested_year]

    for academic_year in target_years:
        _build_search_indexes_for_base(
            f"{ARCHIVE_ROOT}/{academic_year}",
            f"/api/v1/archive/{academic_year}",
            lecture_codes_by_year.get(str(academic_year), {}),
        )

def _get_lecture_code(requested_year: int | None = None):
    target_years = _get_lecture_code_target_years(requested_year)
    lecture_codes_by_year = _load_lecture_codes_by_year()
    _cleanup_expired_archive_data(lecture_codes_by_year)
    current_year = _get_current_academic_year()

    print(f"Start getting lecture codes: {target_years}")
    for academic_year in target_years:
        year_key = str(academic_year)
        lecture_codes = lecture_codes_by_year.get(year_key, {}).copy()
        is_year_fetched = False
        print(f"Getting {academic_year} lecture codes.")

        for dept in tqdm.tqdm(DEPARTMENT):
            # 指定学部の講義コードを取得
            fetched_lecture_codes = get_lecture_code.get_lecture_code(dept, _driver_init, academic_year)
            
            # 講義コード取得失敗時
            if fetched_lecture_codes == None:
                print(f"Failed to get {academic_year} {dept} lecture codes.")
                if dept in lecture_codes:
                    print(f"Keep previous {academic_year} {dept} lecture codes.")
                    continue

                lecture_codes[dept] = None
                print('Skip to get lecture data.')
                continue

            lecture_codes[dept] = fetched_lecture_codes
            is_year_fetched = True

        if not is_year_fetched and not any(value is not None for value in lecture_codes.values()):
            print(f"Failed to get any {academic_year} lecture codes.")
            continue

        lecture_codes_by_year[year_key] = lecture_codes

        if academic_year == current_year:
            _dump_json(LECTURE_CODES_FILE, lecture_codes)

    _cleanup_expired_archive_data(lecture_codes_by_year)
    _dump_json(LECTURE_CODES_BY_YEAR_FILE, lecture_codes_by_year)

def _get_lecture_data(department: str, requested_year: int | None = None):
    target_years = _get_lecture_data_target_years(department, requested_year)
    lecture_codes_by_year = _load_lecture_codes_by_year()
    if _cleanup_expired_archive_data(lecture_codes_by_year):
        _dump_json(LECTURE_CODES_BY_YEAR_FILE, lecture_codes_by_year)

    if not lecture_codes_by_year:
        print("Failed to get lecture data: lecture code files are not found.")
        return

    print(f"Getting {department} lecture data: {target_years}")

    for academic_year in target_years:
        lecture_codes = lecture_codes_by_year.get(str(academic_year))
        if lecture_codes is None:
            print(f"Failed to get lecture data: {academic_year} lecture codes are not found.")
            continue

        department_lecture_codes = lecture_codes.get(department)
        if department_lecture_codes == None:
            print(f"Since {department} is not in {academic_year} lecture_codes, skip to get lecture data.")
            continue
        
        for lecture_code in department_lecture_codes:
            lecture_data = get_timetable.get_timetable(department, lecture_code, academic_year)

            if lecture_data == None:
                print(f"Failed to get {academic_year} {department} lecture data: {lecture_code}")
                continue

            _write_lecture_data(lecture_data, lecture_code, academic_year)

            print(f"Successfully got {academic_year} {department} lecture data: {lecture_code}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-t', '--type', required=True, choices=["lecture_codes", "lecture_data", "indexes"])
    parser.add_argument('-d', '--department', choices=DEPARTMENT)
    parser.add_argument('-y', '--year', type=int)
    args = parser.parse_args()

    if args.type == "lecture_data" and not args.department:
        parser.error("--department is required when type is lecture_data")

    for directory in ["docs", "docs/api", API_ROOT, ARCHIVE_ROOT, "output"]:
        os.makedirs(directory, exist_ok=True)

    if args.type == "lecture_codes":
        try:
            _get_lecture_code(args.year)
        except ValueError as error:
            parser.error(str(error))

    if args.type == "lecture_data":
        try:
            _get_lecture_data(args.department, args.year)
        except ValueError as error:
            parser.error(str(error))

    if args.type == "indexes":
        try:
            _build_indexes(args.year)
        except ValueError as error:
            parser.error(str(error))
