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

#### 年度指定検索(GET)
過去年度のデータは、年度別アーカイブとして保存されます。  
`{年度}`は西暦の年度を指定してください。(例: `2025`)

```
https://tut-timetable-api.pages.dev/api/v1/archive/{年度}/all/{時間割コード}.json
```

#### 学部別サーチインデックス(GET)
クライアント側で講義検索を行うための軽量な学部別一覧です。  
講義名、教員名、曜日・時限、対象学年、教室、絞り込み用キー、詳細JSONへの `path` を返します。曜日・時限・授業科目区分・教員名・開講時期・対象学年・科目区分の絞り込みは、このレスポンス内の `filters` と各講義の `*Key` / `*Keys` を使用してください。

`{学部名}`は、学内で広く認知されている略称を使用し指定します。
以下のリストのいずれかを指定してください。
`["BT", "CS", "MS", "ES", "ESE5", "ESE6", "ESE7", "X1", "DS", "HS", "HSH1", "HSH2", "HSH3", "HSH4", "HSH5", "HSH6", "X3", "GF", "GH"]`

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
> 404 Not Foundが返却された場合は、時間割コードが存在しない可能性があります。
> また、その他のエラーはCloudFlare Pagesのエラーページが返却されます。

#### 学部別サーチインデックス成功時
```
{
    "department": "<学部名>",
    "count": 1,
    "filters": {
        "weekday": [
            {
                "key": "mon",
                "label": "月",
                "count": 1
            }
        ]
    },
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
            "path": "<詳細JSONのパス>",
            "weekdayKeys": [
                "<曜日キー>"
            ],
            "periodKeys": [
                "<時限キー>"
            ],
            "classPeriodKeys": [
                "<曜日時限キー>"
            ],
            "regularOrIntensiveKey": "<授業科目区分キー>",
            "lecturerKeys": [
                "<教員キー>"
            ],
            "courseStartKey": "<開講時期キー>",
            "targetGradeKeys": [
                "<対象学年キー>"
            ],
            "courseTypeKey": "<科目区分キー>"
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

講義データ更新後に、学部別サーチインデックスを `docs/api/v1/search-index/{学部名}.json` と `docs/api/v1/archive/{年度}/search-index/{学部名}.json` に生成します。曜日・時限・`regularOrIntensive`・教員名・開講時期・対象学年・科目区分の絞り込み用キーはサーチインデックスに含まれます。

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
