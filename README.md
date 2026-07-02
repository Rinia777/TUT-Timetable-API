# TUT-Timetable-API

東京工科大学の[学外シラバス](https://kyo-web.teu.ac.jp/campussy)から取得した時間割・講義情報をWebAPIとして提供するプロジェクトです。

Github Actionsを用いて定期実行されるPythonソースファイルにより、学外シラバスのデータ(時間割コード、講義概要など)を取得し、JSON形式で本レポジトリにコミット&プッシュします。
プッシュされたデータは、CloudFlare Pagesを用いて静的JSONファイルとして配信されます。

API URLは `https://tut-timetable-api.pages.dev` です。

## API仕様
### エンドポイント
#### 全体検索(GET)
`{時間割コード}`は、一意に講義を特定できる英数字のコードです。(例: `11040C1`)
```
https://tut-timetable-api.pages.dev/api/v1/all/{時間割コード}.json
```

#### 学部指定検索(GET)
`{時間割コード}`は、一意に講義を特定できる英数字のコードです。(例: `11040C1`)  
`{学部名}`は、学内で広く認知されている略称を使用し指定します。  

以下のリストのいずれかを指定してください。(2024年9月20日時点)  
`["BT", "CS", "MS", "ES", "ESE5", "ESE6", "ESE7", "X1", "DS", "HS", "HSH1", "HSH2", "HSH3", "HSH4", "HSH5", "HSH6", "X3", "GF", "GH"]`
```
https://tut-timetable-api.pages.dev/api/v1/{学部名}/{時間割コード}.json
```

#### 年度指定検索(GET)
過去年度のデータは、年度別アーカイブとして保存されます。  
`{年度}`は西暦の年度を指定してください。(例: `2025`)

```
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/all/{時間割コード}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/{学部名}/{時間割コード}.json
```

#### 絞り込み検索(GET)
曜日・時限・授業科目区分・教員名・開講時期・対象学年・科目区分ごとの講義一覧を取得できます。  
一覧レスポンスは講義詳細そのものではなく、講義概要と詳細JSONへの `path` を返します。

まず、利用可能なキーと件数を `index.json` で確認できます。

```
https://tut-timetable-api.pages.dev/api/v1/index.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index.json
```

曜日は `{曜日キー}` に `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, `sun`, `other` を指定します。

```
https://tut-timetable-api.pages.dev/api/v1/index/weekday/{曜日キー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/weekday/{曜日キー}.json
```

時限は `{時限}` に `1`, `2`, `3`, ... または `other` を指定します。

```
https://tut-timetable-api.pages.dev/api/v1/index/period/{時限}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/period/{時限}.json
```

曜日と時限の組み合わせは `{曜日時限キー}` に `mon-1`, `wed-2`, `fri-5`, `other` などを指定します。

```
https://tut-timetable-api.pages.dev/api/v1/index/class-period/{曜日時限キー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/class-period/{曜日時限キー}.json
```

`regularOrIntensive` は日本語文字列が長いため、`index.json` の `regularOrIntensive[].key` を指定します。

```
https://tut-timetable-api.pages.dev/api/v1/index/regularOrIntensive/{regularOrIntensiveキー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/regularOrIntensive/{regularOrIntensiveキー}.json
```

教員名は `index.json` の `lecturer[].key` を指定します。

```
https://tut-timetable-api.pages.dev/api/v1/index/lecturer/{教員キー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/lecturer/{教員キー}.json
```

開講時期は `index.json` の `courseStart[].key` を指定します。通常は `2026-first` が `2026年度前期`、`2026-second` が `2026年度後期` です。

```
https://tut-timetable-api.pages.dev/api/v1/index/course-start/{開講時期キー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/course-start/{開講時期キー}.json
```

対象学年は `index.json` の `targetGrade[].key` を指定します。通常は `1`, `2`, `3`, `4` です。

```
https://tut-timetable-api.pages.dev/api/v1/index/target-grade/{対象学年キー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/target-grade/{対象学年キー}.json
```

科目区分は `index.json` の `courseType[].key` を指定します。

```
https://tut-timetable-api.pages.dev/api/v1/index/course-type/{科目区分キー}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/index/course-type/{科目区分キー}.json
```

#### 学部別サーチインデックス(GET)
クライアント側で講義検索を行うための軽量な学部別一覧です。  
講義名、教員名、授業科目区分、単位数、詳細JSONへの `path` を返します。

```
https://tut-timetable-api.pages.dev/api/v1/search-index/{学部名}.json
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/search-index/{学部名}.json
```

### レスポンス
レスポンスボディにステータスコード等は含めていません。ステータスコードで200が返却された場合は成功です。  
時間割コードに対応するページデータが1対1で返却されます。
#### 成功時
```
{
    "lectureCode": "<時間割コード>"
    "courseName": "<講義名>",
    "lecturer": [
        "<担当教員>"
    ],
    "regularOrIntensive": "<科目種別>"
    "courseType": "<科目区分>",
    "courseStart": "<開講時期>",
    "classPeriod": [
        "<曜日><時限>"
    ],
    "targetDepartment": "<学部名>",
    "targetGrade": [
        "<対象学年>"
    ],
    "numberOfCredits": <単位数>,
    "classroom": [
        "<教室>"
    ],
    "courceDetails": {
        "courseOverview": "<概要>",
        "outcomesMeasuredBy": "<目標>",
        "learningOutcomes": "<到達目標>",
        "teachingMethod": "<授業計画>",
        "notices": "<履修上の注意>",
        "preparatoryStudy": "<事前学習>",
        "gradingGuidelines": "<成績評価>",
        "textbook": "<教科書>",
        "referenceMaterials": "<参考書>",
        "courseSchedule": "",
        "courseDataUpdatedAt": "<講義詳細更新日>"
    },
    "updateAt": "<レコード更新日>"
}
```

> [!NOTE]
> 404 Not Foundが返却された場合は、時間割コードが存在しないか、指定された学部名が存在しない可能性があります。
> また、その他のエラーはCloudFlare Pagesのエラーページが返却されます。

#### 絞り込み検索成功時
```
{
    "filters": {
        "weekday": "水",
        "weekdayKey": "wed"
    },
    "count": 1,
    "lectures": [
        {
            "lectureCode": "<時間割コード>",
            "courseName": "<講義名>",
            "lecturer": [
                "<担当教員>"
            ],
            "regularOrIntensive": "<科目種別>",
            "courseType": "<科目区分>",
            "courseStart": "<開講時期>",
            "classPeriod": [
                "<曜日><時限>"
            ],
            "targetDepartment": "<学部名>",
            "targetGrade": [
                "<対象学年>"
            ],
            "numberOfCredits": <単位数>,
            "classroom": [
                "<教室>"
            ],
            "updateAt": "<レコード更新日>",
            "path": "<詳細JSONのパス>"
        }
    ]
}
```

#### 学部別サーチインデックス成功時
```
{
    "department": "<学部名>",
    "count": 1,
    "lectures": [
        {
            "courseName": "<講義名>",
            "lecturer": [
                "<担当教員>"
            ],
            "regularOrIntensive": "<科目種別>",
            "numberOfCredits": <単位数>,
            "path": "<詳細JSONのパス>"
        }
    ]
}
```

## 公開設定
Cloudflare Pages で静的APIとして配信します。Pages プロジェクトを以下の設定で作成してください。

```
Project name: tut-timetable-api
Production branch: main
Build command: (leave empty)
Build output directory: docs
```

## データ更新
データの更新は、Github Actionsにより、3ヶ月に一回、JST 15:40 (UTC 6:40)に行われます。

定期実行では現在年度分のみ更新します。過去年度を再取得する場合は `--year` で年度を明示して手動実行します。年度別アーカイブに保存された過去データは削除せず、`docs/api/v1/archive/{年度}/...` に残します。

講義データ更新後に、曜日・時限・`regularOrIntensive`・教員名・開講時期・対象学年・科目区分の絞り込み用インデックスを `docs/api/v1/index...` と `docs/api/v1/archive/{年度}/index...` に生成します。また、学部別サーチインデックスを `docs/api/v1/search-index/{学部名}.json` と `docs/api/v1/archive/{年度}/search-index/{学部名}.json` に生成します。

## 貢献
バグの報告や機能の提案、コードの改善など、どんな形でも貢献を歓迎します。

## ライセンス
MITライセンスです。詳細は[LICENSE](LICENSE)を参照してください。

## 利用にあたって
本プロジェクトは非公式のものであり、片柳学園および東京工科大学とは一切関係ありません。  
本APIを利用したことによるいかなる損害も、本プロジェクトの作成・運営者は責任を負いません。  
また、本APIを利用した派生物の責任も利用者が負うものとします。

### 東京工科大学または片柳学園関係者の方へ
本APIは、システムに負荷がかからない間隔で学外シラバスをスクレイピングし、収集したデータを使用しております。  
万一、本APIの運用に問題がある場合は、ご連絡いただければ対応いたします。
