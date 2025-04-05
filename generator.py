import yaml
import csv
import random
import uuid
import re
from pathlib import Path
from datetime import datetime, timedelta
from faker import Faker
from collections import defaultdict
from typing import Any, Dict, List, Optional

"""
データ生成スクリプト

schema ディレクトリ内の YAML ファイルをもとに、テーブルごとのデータを自動生成し、
output ディレクトリ内に CSV 形式で出力する。

対応するテーブルタイプ:
- master: 一意なマスタデータを生成
- immutable: バージョン管理されたイミュータブルデータ
- transactional: 更新可能なトランザクションデータ
- pointer: 最新バージョンを指し示すポインタテーブル

フィールド定義に応じたデータ型、参照整合性、連番やバージョン管理にも対応。
"""

fake = Faker("ja_JP")

DATA = {}
AUTO_INC = defaultdict(int)
SEQ_COUNTER = defaultdict(int)


def generate_value(field_name: str, field_def: Dict[str, Any], context: Dict[str, Any]) -> Optional[Any]:
    """
    フィールド定義とコンテキスト情報に基づいて、1つのセルの値を生成する。

    Args:
        field_name: フィールド名
        field_def: フィールドの型や制約情報を含む定義
        context: 他のフィールドや親レコードの値を含む文脈

    Returns:
        生成された値（str, int, datetimeなど）
    """
    if field_def.get("nullable", False) and random.random() < 0.1:
        return None
    if "default" in field_def:
        return field_def["default"]

    ftype = field_def.get("type")

    if ftype == "uuid":
        return str(uuid.uuid4())
    elif ftype == "const":
        return field_def.get("value")
    elif ftype == "int":
        return random.randint(field_def.get("min", 0), field_def.get("max", 100))
    elif ftype == "date":
        return fake.date_between(start_date="-1y", end_date="today").isoformat()
    elif ftype == "timestamp":
        dt = fake.date_time_between(start_date="-1y", end_date="now")
        return dt.strftime("%Y-%m-%dT%H:%M:%S")
    elif ftype == "ref":
        ref_table = field_def["table"]
        ref_field = field_def["field"]
        if ref_table not in DATA:
            raise KeyError(f"[ERROR] refテーブル {ref_table} がまだ生成されていません")
        return random.choice(DATA[ref_table])[ref_field]
    elif ftype == "code":
        pattern = field_def.get("pattern", "CODE-{seq:6}")

        def replace(m):
            token = m.group(1)
            if token.startswith("date:"):
                return datetime.today().strftime(token.split(":", 1)[1])
            elif token.startswith("seq:"):
                width = int(token.split(":")[1])
                SEQ_COUNTER[pattern] += 1
                return str(SEQ_COUNTER[pattern]).zfill(width)
            elif token == "alpha":
                return random.choice("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            return f"<UNKNOWN:{token}>"

        return re.sub(r"\{(.*?)\}", replace, pattern)
    elif ftype == "version_sequence":
        return context.get("__version__", 1)
    elif ftype == "auto_increment":
        key = field_name
        AUTO_INC[key] += 1
        return AUTO_INC[key]

    return None


def generate_rows(schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    単一スキーマに基づいて、複数行のデータレコードを生成する。

    Args:
        schema: テーブル定義を含む辞書（type, fields, countなど）

    Returns:
        生成されたレコードのリスト（辞書のリスト）
    """
    if "records" in schema:
        return schema["records"]

    rows = []
    table_type = schema["type"]

    fields = schema.get("fields", {})
    if table_type != "pointer":
        fields = schema["fields"]

    if table_type == "master":
        for _ in range(schema["count"]):
            row = {}
            for name, fdef in fields.items():
                row[name] = generate_value(name, fdef, context=row)
            rows.append(row)

    elif table_type in ("immutable", "transactional") and "parent" in schema:
        parent_table = schema["parent"]
        parent_key_fields = schema.get("parent_key", [])
        if isinstance(parent_key_fields, str):
            parent_key_fields = [parent_key_fields]
        parents = DATA[parent_table]
        count_range = schema.get("count_per_parent", "1").split("~")
        minc = int(count_range[0])
        maxc = int(count_range[-1]) if len(count_range) > 1 else minc

        for parent in parents:
            AUTO_INC.clear()
            for _ in range(random.randint(minc, maxc)):
                row = {}
                for name, fdef in fields.items():
                    ctx = {**row, **parent}
                    if fdef.get("type") == "ref" and fdef["table"] == parent_table and fdef["field"] in parent:
                        row[name] = parent[fdef["field"]]
                    elif fdef.get("type") == "version_sequence":
                        row[name] = parent.get("version", 1)
                    else:
                        row[name] = generate_value(name, fdef, context=ctx)
                rows.append(row)

    elif table_type == "immutable":
        version_range = schema.get("version_range", "1").split("~")
        minv = int(version_range[0])
        maxv = int(version_range[-1]) if len(version_range) > 1 else minv
        for _ in range(schema["count"]):
            base_row = {
                name: generate_value(name, fdef, context={})
                for name, fdef in fields.items()
                if fdef.get("type") != "version_sequence"
            }
            versions = random.randint(minv, maxv)
            for v in range(1, versions + 1):
                context = {"__version__": v, **base_row}
                row = dict(base_row)
                for name, fdef in fields.items():
                    if fdef.get("type") == "version_sequence":
                        row[name] = generate_value(name, fdef, context)
                rows.append(row)

    elif table_type == "transactional":
        for _ in range(schema["count"]):
            row = {}
            for name, fdef in fields.items():
                row[name] = generate_value(name, fdef, context=row)
            rows.append(row)

    elif table_type == "pointer":
        source_table = schema["source_table"]
        key_fields = schema["key"]
        latest_field = schema["latest_field"]

        group = defaultdict(list)
        for row in DATA[source_table]:
            key = tuple(row[k] for k in key_fields)
            group[key].append(row)

        for versions in group.values():
            sorted_versions = sorted(versions, key=lambda r: r[latest_field], reverse=True)
            latest = sorted_versions[0]
            rows.append({k: latest[k] for k in latest})

    return rows


def resolve_dependencies(schemas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    スキーマ間の依存関係を解析し、正しい順序に並べ替える。

    Args:
        schemas: スキーマ定義のリスト

    Returns:
        依存関係順にソートされたスキーマ定義のリスト
    """
    graph = defaultdict(set)
    name_to_schema = {}

    for schema in schemas:
        name = schema["table_name"]
        name_to_schema[name] = schema

        # 全てのref依存を検出
        for field_def in schema.get("fields", {}).values():
            if isinstance(field_def, dict) and field_def.get("type") == "ref":
                ref_table = field_def["table"]
                graph[name].add(ref_table)

        if "parent" in schema:
            graph[name].add(schema["parent"])

        if schema["type"] == "pointer":
            graph[name].add(schema["source_table"])

    visited = set()
    sorted_schemas = []

    def visit(n):
        if n in visited:
            return
        for dep in graph.get(n, []):
            visit(dep)
        visited.add(n)
        sorted_schemas.append(name_to_schema[n])

    for name in name_to_schema:
        visit(name)

    return sorted_schemas


def main() -> None:
    """
    スキーマファイルを読み込み、順にデータを生成して CSV に出力するメイン関数。
    """
    schema_dir = Path("schema")
    output_dir = Path("output")
    output_dir.mkdir(exist_ok=True)

    schemas = []
    for schema_file in sorted(schema_dir.glob("*.yaml")):
        with open(schema_file, encoding="utf-8") as f:
            schema = yaml.safe_load(f)
            schemas.append(schema)

    for schema in resolve_dependencies(schemas):
        table_name = schema["table_name"]
        print(f"[INFO] Generating table: {table_name}")
        rows = generate_rows(schema)
        DATA[table_name] = rows

        if rows:
            with open(output_dir / f"{table_name}.csv", "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(
                    f,
                    fieldnames=rows[0].keys(),
                    quoting=csv.QUOTE_ALL
                )
                writer.writeheader()
                writer.writerows(rows)


if __name__ == "__main__":
    main()