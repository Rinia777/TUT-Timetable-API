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
INDEX_DIRECTORY = "index"
SEARCH_INDEX_DIRECTORY = "search-index"

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
SUMMARY_FIELDS = [
    "lectureCode",
    "courseName",
    "lecturer",
    "regularOrIntensive",
    "courseType",
    "courseStart",
    "classPeriod",
    "targetDepartment",
    "targetGrade",
    "numberOfCredits",
    "classroom",
    "updateAt",
]

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
    if requested_year is not None:
        return [requested_year]

    return [_get_current_academic_year()]

def _get_lecture_data_target_years(department: str, requested_year: int | None = None) -> list[int]:
    if requested_year is not None:
        return [requested_year]

    return [_get_current_academic_year()]

def _write_lecture_data(lecture_data: dict, department: str, lecture_code: str, academic_year: int) -> None:
    current_year = _get_current_academic_year()

    archive_department_path = f"{ARCHIVE_ROOT}/{academic_year}/{department}/{lecture_code}.json"
    archive_all_path = f"{ARCHIVE_ROOT}/{academic_year}/all/{lecture_code}.json"
    _dump_json(archive_department_path, lecture_data)
    _dump_json(archive_all_path, lecture_data)

    if academic_year != current_year:
        return

    latest_department_path = f"{API_ROOT}/{department}/{lecture_code}.json"
    latest_all_path = f"{API_ROOT}/all/{lecture_code}.json"
    _dump_json(latest_department_path, lecture_data)
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

def _get_lecture_summary(lecture_data: dict, api_prefix: str) -> dict:
    summary = {
        field: lecture_data.get(field)
        for field in SUMMARY_FIELDS
        if field in lecture_data
    }
    lecture_code = lecture_data.get("lectureCode")
    if lecture_code:
        summary["path"] = f"{api_prefix}/all/{lecture_code}.json"

    return summary

def _get_search_index_entry(lecture_data: dict, api_prefix: str, department: str, lecture_code: str) -> dict:
    return {
        "courseName": lecture_data.get("courseName"),
        "lecturer": lecture_data.get("lecturer"),
        "regularOrIntensive": lecture_data.get("regularOrIntensive"),
        "numberOfCredits": lecture_data.get("numberOfCredits"),
        "path": f"{api_prefix}/{department}/{lecture_code}.json",
    }

def _sort_lecture_summaries(lectures: dict) -> list[dict]:
    return sorted(
        lectures.values(),
        key=lambda lecture: (
            str(lecture.get("courseStart") or ""),
            str(lecture.get("classPeriod") or ""),
            str(lecture.get("lectureCode") or ""),
        )
    )

def _build_filter_response(filters: dict, lectures: dict) -> dict:
    sorted_lectures = _sort_lecture_summaries(lectures)
    return {
        "filters": filters,
        "count": len(sorted_lectures),
        "lectures": sorted_lectures,
    }

def _add_to_index(indexes: dict, index_key: str, lecture_summary: dict) -> None:
    lecture_code = lecture_summary.get("lectureCode")
    if not lecture_code:
        return

    indexes.setdefault(index_key, {})[lecture_code] = lecture_summary

def _write_named_indexes(
    index_root: str,
    api_prefix: str,
    directory_name: str,
    index_data: dict,
    filter_name: str,
    label_getter,
    sort_key_getter=None,
) -> list[dict]:
    items = []

    if sort_key_getter is None:
        sort_key_getter = lambda key: key

    for key in sorted(index_data, key=sort_key_getter):
        label = label_getter(key)
        path = f"{api_prefix}/{INDEX_DIRECTORY}/{directory_name}/{key}.json"
        lectures = index_data[key]
        _dump_json(
            f"{index_root}/{directory_name}/{key}.json",
            _build_filter_response({filter_name: label, f"{filter_name}Key": key}, lectures)
        )
        items.append({
            "key": key,
            "label": label,
            "count": len(lectures),
            "path": path,
        })

    return items

def _build_indexes_for_base(base_path: str, api_prefix: str) -> bool:
    all_directory = f"{base_path}/all"
    if not os.path.isdir(all_directory):
        print(f"Skip indexes: {all_directory} is not found.")
        return False

    index_root = f"{base_path}/{INDEX_DIRECTORY}"
    if os.path.isdir(index_root):
        shutil.rmtree(index_root)

    weekday_indexes = {}
    period_indexes = {}
    class_period_indexes = {}
    regular_or_intensive_indexes = {}
    regular_or_intensive_labels = {}
    lecturer_indexes = {}
    lecturer_labels = {}
    course_start_indexes = {}
    course_start_labels = {}
    target_grade_indexes = {}
    target_grade_labels = {}
    course_type_indexes = {}
    course_type_labels = {}

    for file_name in sorted(os.listdir(all_directory)):
        if not file_name.endswith(".json"):
            continue

        lecture_path = f"{all_directory}/{file_name}"
        lecture_data = _load_json(lecture_path, None)
        if lecture_data is None:
            continue

        lecture_summary = _get_lecture_summary(lecture_data, api_prefix)
        weekdays, periods, class_periods = _get_schedule_keys(_as_list(lecture_data.get("classPeriod")))

        for weekday in weekdays:
            _add_to_index(weekday_indexes, weekday, lecture_summary)

        for period in periods:
            _add_to_index(period_indexes, period, lecture_summary)

        for class_period in class_periods:
            _add_to_index(class_period_indexes, class_period, lecture_summary)

        regular_or_intensive = lecture_data.get("regularOrIntensive") or ""
        regular_or_intensive_id = _get_regular_or_intensive_id(regular_or_intensive)
        regular_or_intensive_labels[regular_or_intensive_id] = regular_or_intensive
        _add_to_index(regular_or_intensive_indexes, regular_or_intensive_id, lecture_summary)

        for lecturer in _as_list(lecture_data.get("lecturer")):
            lecturer = str(lecturer or "")
            lecturer_id = _get_hashed_id(lecturer)
            lecturer_labels[lecturer_id] = lecturer
            _add_to_index(lecturer_indexes, lecturer_id, lecture_summary)

        course_start = lecture_data.get("courseStart") or ""
        course_start_id = _get_course_start_id(course_start)
        course_start_labels[course_start_id] = course_start
        _add_to_index(course_start_indexes, course_start_id, lecture_summary)

        for target_grade in _as_list(lecture_data.get("targetGrade")):
            target_grade = str(target_grade or "")
            target_grade_id = _get_target_grade_id(target_grade)
            target_grade_labels[target_grade_id] = target_grade
            _add_to_index(target_grade_indexes, target_grade_id, lecture_summary)

        course_type = lecture_data.get("courseType") or ""
        course_type_id = _get_hashed_id(course_type)
        course_type_labels[course_type_id] = course_type
        _add_to_index(course_type_indexes, course_type_id, lecture_summary)

    weekday_items = _write_named_indexes(
        index_root,
        api_prefix,
        "weekday",
        weekday_indexes,
        "weekday",
        lambda key: WEEKDAY_LABELS.get(key, key),
    )
    period_items = _write_named_indexes(
        index_root,
        api_prefix,
        "period",
        period_indexes,
        "period",
        lambda key: "他" if key == "other" else key,
    )
    class_period_items = _write_named_indexes(
        index_root,
        api_prefix,
        "class-period",
        class_period_indexes,
        "classPeriod",
        lambda key: "他" if key == "other" else f"{WEEKDAY_LABELS[key.split('-')[0]]}{key.split('-')[1]}",
    )

    regular_or_intensive_items = []
    for key in sorted(regular_or_intensive_indexes, key=lambda item: regular_or_intensive_labels.get(item, "")):
        regular_or_intensive = regular_or_intensive_labels[key]
        lectures = regular_or_intensive_indexes[key]
        path = f"{api_prefix}/{INDEX_DIRECTORY}/regularOrIntensive/{key}.json"
        _dump_json(
            f"{index_root}/regularOrIntensive/{key}.json",
            _build_filter_response(
                {
                    "regularOrIntensive": regular_or_intensive,
                    "regularOrIntensiveKey": key,
                },
                lectures,
            )
        )
        regular_or_intensive_items.append({
            "key": key,
            "label": regular_or_intensive,
            "count": len(lectures),
            "path": path,
        })

    lecturer_items = _write_named_indexes(
        index_root,
        api_prefix,
        "lecturer",
        lecturer_indexes,
        "lecturer",
        lambda key: lecturer_labels.get(key, ""),
        lambda key: lecturer_labels.get(key, ""),
    )
    course_start_items = _write_named_indexes(
        index_root,
        api_prefix,
        "course-start",
        course_start_indexes,
        "courseStart",
        lambda key: course_start_labels.get(key, ""),
        lambda key: course_start_labels.get(key, ""),
    )
    target_grade_items = _write_named_indexes(
        index_root,
        api_prefix,
        "target-grade",
        target_grade_indexes,
        "targetGrade",
        lambda key: target_grade_labels.get(key, ""),
        lambda key: int(key) if key.isdigit() else 9999,
    )
    course_type_items = _write_named_indexes(
        index_root,
        api_prefix,
        "course-type",
        course_type_indexes,
        "courseType",
        lambda key: course_type_labels.get(key, ""),
        lambda key: course_type_labels.get(key, ""),
    )

    metadata = {
        "endpoints": {
            "weekday": f"{api_prefix}/{INDEX_DIRECTORY}/weekday/{{weekdayKey}}.json",
            "period": f"{api_prefix}/{INDEX_DIRECTORY}/period/{{period}}.json",
            "classPeriod": f"{api_prefix}/{INDEX_DIRECTORY}/class-period/{{classPeriodKey}}.json",
            "regularOrIntensive": f"{api_prefix}/{INDEX_DIRECTORY}/regularOrIntensive/{{regularOrIntensiveKey}}.json",
            "lecturer": f"{api_prefix}/{INDEX_DIRECTORY}/lecturer/{{lecturerKey}}.json",
            "courseStart": f"{api_prefix}/{INDEX_DIRECTORY}/course-start/{{courseStartKey}}.json",
            "targetGrade": f"{api_prefix}/{INDEX_DIRECTORY}/target-grade/{{targetGradeKey}}.json",
            "courseType": f"{api_prefix}/{INDEX_DIRECTORY}/course-type/{{courseTypeKey}}.json",
        },
        "weekday": weekday_items,
        "period": period_items,
        "classPeriod": class_period_items,
        "regularOrIntensive": regular_or_intensive_items,
        "lecturer": lecturer_items,
        "courseStart": course_start_items,
        "targetGrade": target_grade_items,
        "courseType": course_type_items,
    }
    _dump_json(f"{base_path}/index.json", metadata)

    print(f"Built indexes: {api_prefix}")
    return True

def _build_search_indexes_for_base(base_path: str, api_prefix: str) -> bool:
    search_index_root = f"{base_path}/{SEARCH_INDEX_DIRECTORY}"
    if os.path.isdir(search_index_root):
        shutil.rmtree(search_index_root)

    built_count = 0
    for department in DEPARTMENT:
        department_directory = f"{base_path}/{department}"
        if not os.path.isdir(department_directory):
            continue

        lectures = []
        for file_name in sorted(os.listdir(department_directory)):
            if not file_name.endswith(".json"):
                continue

            lecture_code = file_name[:-5]
            lecture_data = _load_json(f"{department_directory}/{file_name}", None)
            if lecture_data is None:
                continue

            lectures.append(_get_search_index_entry(lecture_data, api_prefix, department, lecture_code))

        lectures.sort(key=lambda lecture: (
            str(lecture.get("courseName") or ""),
            str(lecture.get("path") or ""),
        ))
        _dump_json(
            f"{search_index_root}/{department}.json",
            {
                "department": department,
                "count": len(lectures),
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
    if requested_year is None:
        _build_indexes_for_base(API_ROOT, "/api/v1")
        _build_search_indexes_for_base(API_ROOT, "/api/v1")
        target_years = _get_archive_years()
    else:
        target_years = [requested_year]

    for academic_year in target_years:
        _build_indexes_for_base(
            f"{ARCHIVE_ROOT}/{academic_year}",
            f"/api/v1/archive/{academic_year}",
        )
        _build_search_indexes_for_base(
            f"{ARCHIVE_ROOT}/{academic_year}",
            f"/api/v1/archive/{academic_year}",
        )

def _get_lecture_code(requested_year: int | None = None):
    lecture_codes_by_year = _load_lecture_codes_by_year()
    target_years = _get_lecture_code_target_years(requested_year)
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

    _dump_json(LECTURE_CODES_BY_YEAR_FILE, lecture_codes_by_year)

def _get_lecture_data(department: str, requested_year: int | None = None):
    lecture_codes_by_year = _load_lecture_codes_by_year()
    if not lecture_codes_by_year:
        print("Failed to get lecture data: lecture code files are not found.")
        return

    target_years = _get_lecture_data_target_years(department, requested_year)
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

            _write_lecture_data(lecture_data, department, lecture_code, academic_year)

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
        _get_lecture_code(args.year)

    if args.type == "lecture_data":
        _get_lecture_data(args.department, args.year)

    if args.type == "indexes":
        _build_indexes(args.year)
