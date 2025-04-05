# YAML スキーマ定義仕様

---

整合性のあるテストデータを自動生成するために、各テーブル定義を YAML ファイルで記述します。ここではその書き方のルールを説明します。

---

## 📁 配置場所

- YAML ファイルはすべて `schema/` フォルダ配下に置きます。

---

## 🔧 共通プロパティ

| キー名           | 必須 | 説明                                                       |
|---------------|----|----------------------------------------------------------|
| `table_name`  | ✅  | テーブル名（CSVファイル名としても使用）                                    |
| `type`        | ✅  | テーブル種別：`master`, `immutable`, `pointer`, `transactional` |
| `primary_key` | ✅  | 主キーのフィールド名（複数可）                                          |
| `fields`      | -  | 各カラムの定義。`records` がない場合に必要                               |
| `records`     | -  | 固定レコード定義（ステータスなど少数固定値のマスタ向け）                             |
| `count`       | -  | 自動生成件数。`fields` 定義時に必要                                   |

---

## 📘 テーブル種別の説明

### `master`

固定データを表すマスタテーブルです。主に参照用のデータを提供します。

- `count` を指定して自動生成するか、
- `records` を使って明示的に定義する

### `immutable`

イミュータブル（不変）データで、過去の状態を保持するために使用されます。

- `version_range`: バージョンの生成数（例: `1~3`）
- バージョン番号には `version_sequence` を使用

### `transactional`

更新可能なトランザクションデータで、動的なビジネスプロセスを表現します。

### `pointer`

イミュータブルテーブルの中から最新のレコードを指し示すポインタテーブルです。

- `source_table`: 抽出元テーブル名
- `key`: レコードを特定するキー（複合キーも可）
- `latest_field`: バージョンを示すフィールド名

---

## 🔠 フィールド型（`type`）一覧

| 型名                 | 内容                                                |
|--------------------|---------------------------------------------------|
| `uuid`             | UUID形式で一意な文字列を生成                                  |
| `const`            | 固定値を出力（`value` を指定）                               |
| `int`              | 整数を生成（`min`, `max`）                               |
| `date`             | ランダムな過去日付（`YYYY-MM-DD`）                           |
| `timestamp`        | タイムスタンプ（`YYYY-MM-DDTHH:MM:SS`、ミリ秒なし）              |
| `ref`              | 他テーブルからランダムに参照（`table`, `field` を指定）              |
| `code`             | `{seq:3}`, `{date:%Y%m%d}`, `{alpha}` などを使って文字列生成 |
| `version_sequence` | `immutable` のバージョン番号（1からの連番）                      |
| `auto_increment`   | サロゲートキーや明細行番号などの連番                                |

---

## 🧩 その他の属性

| 属性名                | 型      | 説明                                           |
|--------------------|--------|----------------------------------------------|
| `nullable`         | bool   | `true` の場合、約10%の確率で null を出力                 |
| `default`          | 任意型    | 値が未指定のときに使用されるデフォルト値                         |
| `unique`           | bool   | `true` の場合、生成される値が一意になるよう保証                  |
| `parent`           | string | 親テーブルの名前を指定します。子テーブルが親テーブルの情報を参照するために使用されます。 |
| `parent_key`       | string | 親テーブルの主キーを指定します。子テーブルが親テーブルの情報を参照するために必要です。  |
| `count_per_parent` | string | 各親レコードに対して生成する子レコードの件数を指定します。                |

---

## 📝 `code` のパターン指定例

| パターン            | 説明                 | 出力例               |
|-----------------|--------------------|-------------------|
| `{seq:3}`       | 連番3桁               | `001`, `002`, ... |
| `{date:%Y%m%d}` | 現在日付の埋め込み          | `20250405`        |
| `{alpha}`       | ランダムな大文字アルファベット1文字 | `A`, `B`, ...     |

---

## ✅ サンプル：マスタテーブル（count指定）

```yaml
table_name: item_master
type: master
primary_key: [item_id]
count: 5
fields:
  item_id:
    type: code
    pattern: "ITEM-{seq:3}"
    unique: true
  item_name:
    type: const
    value: "商品"
```

---

## ✅ サンプル：マスタテーブル（records指定）

```yaml
table_name: item_status_master
type: master
primary_key: [item_status_id]
records:
  - item_status_id: GOOD
    item_status_name: 良品
  - item_status_id: DEFECT
    item_status_name: 不良品
  - item_status_id: HOLD
    item_status_name: 保留
```

---

## ✅ サンプル：イミュータブルテーブル

```yaml
table_name: inventory
type: immutable
primary_key: [location_id, item_id, version]
count: 10
version_range: 1~3
fields:
  location_id:
    type: ref
    table: location_master
    field: location_id
  item_id:
    type: ref
    table: item_master
    field: item_id
  quantity:
    type: int
    min: 0
    max: 1000
  version:
    type: version_sequence
  updated_at:
    type: timestamp
```

---

## ✅ サンプル：トランザクションテーブル

```yaml
table_name: shipment_transaction
type: transactional
primary_key: [shipment_id]
count: 20
fields:
  shipment_id:
    type: code
    pattern: "SHIP-{seq:4}"
    unique: true
  from_location_id:
    type: ref
    table: location_master
    field: location_id
  to_location_id:
    type: ref
    table: location_master
    field: location_id
  shipment_date:
    type: date
```

---

## ✅ サンプル：親子関係

### 親

```yaml
table_name: slip_header
type: immutable
primary_key: [slip_number, version]
count: 10
version_range: 1~2
fields:
  slip_number:
    type: code
    pattern: "SLIP-{seq:4}"
    unique: true
  from_location_id:
    type: ref
    table: location_master
    field: location_id
  to_location_id:
    type: ref
    table: location_master
    field: location_id
  version:
    type: version_sequence
  shipment_date:
    type: date
```

### 子

```yaml
table_name: slip_detail
type: immutable
primary_key: [slip_number, detail_no]
parent: slip_header
parent_key: slip_number
count_per_parent: 1~3
fields:
  slip_number:
    type: ref
    table: slip_header
    field: slip_number
  version:
    type: ref
    table: slip_header
    field: version
  detail_no:
    type: auto_increment
  item_id:
    type: ref
    table: item_master
    field: item_id
  quantity:
    type: int
    min: 1
    max: 100
```

---

## ✅ サンプル：ポインタテーブル（最新バージョンを参照）

```yaml
table_name: slip_header_pointer
type: pointer
source_table: slip_header
key: [slip_number]
latest_field: version  # latest_field は最大値（最新）を示すカラムを指定
```

---

## 🚀 データ生成の実行方法

```bash
python generator.py
```

- 結果は `output/` ディレクトリ配下に CSV 形式で出力されます。
- すべての値はダブルクォート (`"`) で囲まれています。

---

## ❓ 補足事項と注意事項

- `table_name` は一意でなければなりません。同じ名前のテーブルを複数定義することはできません。
- `primary_key` は1つ以上指定する必要があります。指定するフィールドは `fields` または `records` に必ず存在する必要があります。
- `fields` と `records` はどちらか一方のみを記述してください。両方を同時に指定することはできません。
- `count` の値が0以下の場合、自動生成は行われず空データになります。
- `type: master` の場合でも、適宜 `records` を使用することで固定値マスタを簡易的に記述可能です。
- カラム定義の際、`nullable: true` を指定すると一部の値が `null` になりますが、`primary_key` のカラムには指定できません。
- `unique: true` の属性を付けたフィールドは、生成値が衝突しないように保証されますが、生成件数によっては生成に失敗する場合があります。その場合、`count` を調整してください。
- `ref` フィールドが依存するテーブルは YAML ファイル上で先に記述されていなくても順序解決されます。

---

## 🔄 更新方法・仕様追加

新しい型や仕様を追加した場合は、この `README.md` を更新してください。