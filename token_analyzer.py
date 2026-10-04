"""
自动扫描 Windows 本地与 WSL2 环境下的 Antigravity / Gemini 会话数据库并提取全量 Token 调用数据
"""
import glob
import os
import sqlite3
import subprocess
from typing import Any, Dict, List, Optional, Union
from proto_decoder import extract_gen_metadata


def detect_wsl_distros() -> List[str]:
    """探测已安装的 WSL2 发行版名称列表"""
    distros: List[str] = []
    # 1. 尝试通过 wsl.exe -l -q 查询
    try:
        out = subprocess.check_output(
            ["wsl.exe", "-l", "-q"],
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        # Windows 控制台下 wsl.exe 输出通常为 utf-16le 编码
        decoded = out.decode("utf-16le", errors="ignore")
        for line in decoded.splitlines():
            name = line.strip().replace("\x00", "")
            if name and name not in distros:
                distros.append(name)
    except Exception:
        pass

    # 2. 备选方案：检查常见的默认发行版 UNC 路径是否存在
    fallback_candidates = [
        "Ubuntu", "Ubuntu-24.04", "Ubuntu-22.04", "Ubuntu-20.04",
        "Debian", "kali-linux", "openSUSE-Leap-15.5", "Arch"
    ]
    for d in fallback_candidates:
        if d not in distros:
            if os.path.exists(rf"\\wsl.localhost\{d}") or os.path.exists(rf"\\wsl$\{d}"):
                distros.append(d)

    return distros


def discover_all_data_dirs() -> List[Dict[str, str]]:
    """
    自动发现所有潜在的数据根目录，包括：
    1. Windows 本地环境：~/.gemini, ~/.antigravity 等
    2. WSL2 环境：各发行版下的 /root/.gemini, /root/.antigravity, /home/*/.gemini, /home/*/.antigravity 等
    返回格式：[{"env": "windows", "path": "..."}, {"env": "wsl2:Ubuntu", "path": "..."}, ...]
    """
    scan_targets: List[Dict[str, str]] = []
    added_paths = set()

    def add_target(env: str, p: str):
        norm = os.path.normcase(os.path.abspath(p))
        if norm not in added_paths and os.path.isdir(p):
            added_paths.add(norm)
            scan_targets.append({"env": env, "path": p})

    # --- 1. Windows 本地目录自适应发现 ---
    home_dir = os.path.expanduser("~")
    win_candidates = [
        os.path.join(home_dir, ".gemini"),
        os.path.join(home_dir, ".antigravity"),
    ]
    # 枚举系统驱动盘下所有用户目录 (自适应任何机型与用户名)
    system_drive = os.environ.get("SystemDrive", "C:")
    users_root = os.path.join(system_drive, "\\Users")
    if os.path.isdir(users_root):
        system_ignore = {"public", "default", "default user", "all users", "desktop.ini"}
        try:
            for entry in os.listdir(users_root):
                if entry.lower() in system_ignore:
                    continue
                user_path = os.path.join(users_root, entry)
                if os.path.isdir(user_path):
                    win_candidates.append(os.path.join(user_path, ".gemini"))
                    win_candidates.append(os.path.join(user_path, ".antigravity"))
        except Exception:
            pass

    for p in win_candidates:
        if os.path.exists(p):
            add_target("windows", p)

    # --- 2. WSL2 环境探测与目录遍历 ---
    distros = detect_wsl_distros()
    for d in distros:
        base_prefix = None
        for prefix in [rf"\\wsl.localhost\{d}", rf"\\wsl$\{d}"]:
            if os.path.exists(prefix):
                base_prefix = prefix
                break
        if not base_prefix:
            continue

        wsl_candidates = [
            os.path.join(base_prefix, "root", ".gemini"),
            os.path.join(base_prefix, "root", ".antigravity"),
        ]
        # 扫描 /home/ 各用户目录
        home_path = os.path.join(base_prefix, "home")
        if os.path.exists(home_path):
            try:
                for user_dir in os.listdir(home_path):
                    user_full = os.path.join(home_path, user_dir)
                    if os.path.isdir(user_full):
                        wsl_candidates.append(os.path.join(user_full, ".gemini"))
                        wsl_candidates.append(os.path.join(user_full, ".antigravity"))
            except Exception:
                pass

        for c in wsl_candidates:
            if os.path.exists(c):
                add_target(f"wsl2:{d}", c)

    return scan_targets


def scan_all_conversation_dbs(
    base_dirs: Optional[Union[str, List[Union[str, Dict[str, str]]]]] = None
) -> List[Dict[str, str]]:
    """
    检索 base_dirs 下所有 conversations 文件夹中的 .db 文件
    返回字典列表：[{"path": db_path, "env": env_label}, ...]
    """
    targets: List[Dict[str, str]] = []

    if base_dirs is None:
        targets = discover_all_data_dirs()
    elif isinstance(base_dirs, str):
        env_label = "wsl2" if ("wsl.localhost" in base_dirs or "wsl$" in base_dirs) else "windows"
        targets = [{"env": env_label, "path": base_dirs}]
    elif isinstance(base_dirs, list):
        for item in base_dirs:
            if isinstance(item, dict):
                targets.append(item)
            elif isinstance(item, str):
                env_label = "wsl2" if ("wsl.localhost" in item or "wsl$" in item) else "windows"
                targets.append({"env": env_label, "path": item})

    all_dbs: List[Dict[str, str]] = []
    seen_db_paths = set()

    for target in targets:
        env = target["env"]
        p = target["path"]
        pattern = os.path.join(p, "**", "conversations", "*.db")
        db_files = glob.glob(pattern, recursive=True)
        for db in sorted(db_files):
            norm = os.path.normcase(os.path.abspath(db))
            if norm not in seen_db_paths:
                seen_db_paths.add(norm)
                all_dbs.append({"path": db, "env": env})

    return all_dbs


def parse_single_db(db_path: str, env: str = "windows") -> List[Dict[str, Any]]:
    """
    解析单个 SQLite 数据库中的 gen_metadata 记录
    支持 Windows 本地文件及 WSL2 UNC 路径，使用只读不可变模式规避文件锁冲突
    同时识别属于 Antigravity IDE 还是 Antigravity CLI
    """
    records = []
    db_filename = os.path.basename(db_path)
    conv_id = os.path.splitext(db_filename)[0]

    # 构建适用于 SQLite 的 URI 路径
    norm_path = os.path.normpath(db_path).replace("\\", "/")
    if norm_path.startswith("//"):
        # Windows UNC 网络路径，如 //wsl.localhost/Ubuntu/...
        uri = f"file:////{norm_path.lstrip('/')}?mode=ro&immutable=1"
    else:
        # 本地盘符路径，如 file:C:/Users/...
        uri = f"file:{norm_path}?mode=ro&immutable=1"

    # 识别客户端工具类型 (IDE vs CLI vs 其他)
    norm_lower = norm_path.lower()
    if "antigravity-cli" in norm_lower:
        client_type = "Antigravity CLI"
    elif "antigravity-ide" in norm_lower:
        client_type = "Antigravity IDE"
    elif "antigravity" in norm_lower:
        client_type = "Antigravity"
    else:
        client_type = "Antigravity IDE"

    try:
        conn = sqlite3.connect(uri, uri=True)
        cursor = conn.cursor()

        # 检查是否存在 gen_metadata 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='gen_metadata';")
        if not cursor.fetchone():
            conn.close()
            return []

        # 尝试获取 trajectory_meta 中的元数据
        meta_info = {}
        try:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trajectory_meta';")
            if cursor.fetchone():
                cursor.execute("SELECT * FROM trajectory_meta LIMIT 1;")
                row = cursor.fetchone()
                if row:
                    col_names = [d[0] for d in cursor.description]
                    meta_info = dict(zip(col_names, row))
        except Exception:
            pass

        # 读取 gen_metadata 表
        cursor.execute("SELECT idx, data, size FROM gen_metadata ORDER BY idx ASC;")
        rows = cursor.fetchall()
        for idx, data_blob, size in rows:
            if not data_blob:
                continue
            item = extract_gen_metadata(data_blob)
            if item:
                item['db_file'] = db_filename
                item['db_path'] = db_path
                item['conv_id'] = conv_id
                item['step_idx'] = idx
                item['blob_size'] = size
                item['env'] = env
                item['client_type'] = client_type
                if meta_info:
                    item['trajectory_type'] = meta_info.get('trajectory_type')
                    item['source'] = meta_info.get('source')
                records.append(item)

        conn.close()
    except Exception as e:
        # print(f"Error reading {db_path}: {e}")
        pass

    return records


def collect_all_data(
    base_dirs: Optional[Union[str, List[Union[str, Dict[str, str]]]]] = None
) -> List[Dict[str, Any]]:
    """
    扫描所有已发现的数据库（包含 Windows 本地与 WSL2 环境）并返回全部 Token 记录列表
    提供按 (conv_id, step_idx) 的全局去重保护
    """
    db_items = scan_all_conversation_dbs(base_dirs)
    
    # 统计各环境数据库数量
    env_counts: Dict[str, int] = {}
    for item in db_items:
        env = item["env"]
        env_counts[env] = env_counts.get(env, 0) + 1

    summary_parts = [f"{env}: {count} 个" for env, count in env_counts.items()]
    print(f"找到 {len(db_items)} 个数据库文件 ({', '.join(summary_parts)})，正在解析...")

    all_records = []
    seen_steps = set()

    for item in db_items:
        db_path = item["path"]
        env = item["env"]
        db_records = parse_single_db(db_path, env=env)
        for r in db_records:
            dedup_key = (r["conv_id"], r["step_idx"])
            if dedup_key not in seen_steps:
                seen_steps.add(dedup_key)
                all_records.append(r)

    print(f"解析完成！累计成功提取 {len(all_records)} 条模型调用元数据记录。")
    return all_records


if __name__ == '__main__':
    targets = discover_all_data_dirs()
    print("自动发现的数据目录目标:")
    for t in targets:
        print(f" - [{t['env']}] {t['path']}")
    recs = collect_all_data()
    print("样例记录:", recs[0] if recs else "None")
