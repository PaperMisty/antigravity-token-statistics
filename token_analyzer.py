"""
自动扫描 Windows 本地与 WSL2 环境下的 Antigravity / Gemini 会话数据库并提取全量 Token 调用数据
"""
import glob
import json
import os
import sqlite3
import subprocess
import time
from typing import Any, Dict, List, Optional, Union
from proto_decoder import extract_gen_metadata


_WSL_DISTROS_CACHE: Optional[List[str]] = None


def detect_wsl_distros(force_refresh: bool = False) -> List[str]:
    """
    探测已安装的 WSL2 发行版名称列表
    优先使用 Windows 注册表秒级探测 (耗时 < 0.001s)，彻底规避 UNC 网络超时与 wsl.exe 进程开销
    """
    global _WSL_DISTROS_CACHE
    if _WSL_DISTROS_CACHE is not None and not force_refresh:
        return _WSL_DISTROS_CACHE

    distros: List[str] = []

    # 1. 优先通过 Windows 注册表枚举 (仅需不到 1 毫秒且 100% 精确)
    try:
        import winreg
        lxss_key_path = r"Software\Microsoft\Windows\CurrentVersion\Lxss"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, lxss_key_path) as key:
            i = 0
            while True:
                try:
                    subkey_name = winreg.EnumKey(key, i)
                    with winreg.OpenKey(key, subkey_name) as subkey:
                        name, _ = winreg.QueryValueEx(subkey, "DistributionName")
                        if name and name not in distros:
                            distros.append(str(name))
                    i += 1
                except OSError:
                    break
    except Exception:
        pass

    # 2. 备用：如果注册表未找到且强制刷新，尝试运行 wsl.exe -l -q
    if not distros and (force_refresh or os.name == "nt"):
        try:
            out = subprocess.check_output(
                ["wsl.exe", "-l", "-q"],
                stderr=subprocess.DEVNULL,
                timeout=1.5
            )
            decoded = out.decode("utf-16le", errors="ignore")
            for line in decoded.splitlines():
                name = line.strip().replace("\x00", "")
                if name and name not in distros:
                    distros.append(name)
        except Exception:
            pass

    _WSL_DISTROS_CACHE = distros
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
    采用精准深度匹配，杜绝全局递归 (**) 导致的磁盘与网络 I/O 阻塞
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
        # 精准匹配：antigravity-ide/conversations/*.db, antigravity-cli/conversations/*.db, conversations/*.db
        db_files = []
        db_files.extend(glob.glob(os.path.join(p, "*", "conversations", "*.db")))
        db_files.extend(glob.glob(os.path.join(p, "conversations", "*.db")))
        if not db_files:
            # 备用方案：两级子目录
            db_files.extend(glob.glob(os.path.join(p, "*", "*", "conversations", "*.db")))

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


def load_token_cache(cache_file: str) -> Dict[str, Any]:
    """加载本地增量缓存，若不存在或损坏则返回空缓存结构"""
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and data.get("version") == 1 and "files" in data:
                    return data
        except Exception:
            pass
    return {"version": 1, "last_updated": 0, "files": {}}


def save_token_cache(cache_file: str, cache_data: Dict[str, Any]) -> None:
    """原子保存增量缓存文件"""
    tmp_file = f"{cache_file}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, ensure_ascii=False)
        if os.path.exists(cache_file):
            os.remove(cache_file)
        os.rename(tmp_file, cache_file)
    except Exception:
        try:
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, ensure_ascii=False)
        except Exception:
            pass


def collect_all_data(
    base_dirs: Optional[Union[str, List[Union[str, Dict[str, str]]]]] = None,
    use_cache: bool = True,
    cache_file: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    扫描所有已发现的数据库（包含 Windows 本地与 WSL2 环境）并返回全部 Token 记录列表
    - 支持基于文件修改时间 (mtime) 与大小 (size) 的本地增量缓存机制
    - 未修改的历史会话直接毫秒级读取缓存，仅解析有新增或变更的数据库
    - 提供按 (conv_id, step_idx) 的全局去重保护
    """
    if cache_file is None:
        cache_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".token_cache.json")

    db_items = scan_all_conversation_dbs(base_dirs)
    
    # 统计各环境数据库数量
    env_counts: Dict[str, int] = {}
    for item in db_items:
        env = item["env"]
        env_counts[env] = env_counts.get(env, 0) + 1

    summary_parts = [f"{env}: {count} 个" for env, count in env_counts.items()]
    total_dbs = len(db_items)

    cache_data = load_token_cache(cache_file) if use_cache else {"version": 1, "files": {}}
    cached_files = cache_data.get("files", {})

    all_records = []
    seen_steps = set()
    cache_hit_count = 0
    parsed_count = 0
    cache_modified = False

    current_db_keys = set()

    for item in db_items:
        db_path = item["path"]
        env = item["env"]
        norm_key = os.path.normcase(os.path.abspath(db_path))
        current_db_keys.add(norm_key)

        mtime = 0.0
        size = 0
        try:
            st = os.stat(db_path)
            mtime = st.st_mtime
            size = st.st_size
        except Exception:
            pass

        # 检查是否命中增量缓存
        cached_entry = cached_files.get(norm_key)
        if (
            use_cache
            and cached_entry
            and abs(cached_entry.get("mtime", 0) - mtime) < 1e-4
            and cached_entry.get("size") == size
            and "records" in cached_entry
        ):
            db_records = cached_entry["records"]
            cache_hit_count += 1
        else:
            # 文件发生新增或变更，重新解析该数据库
            db_records = parse_single_db(db_path, env=env)
            parsed_count += 1
            cache_modified = True
            if use_cache:
                cached_files[norm_key] = {
                    "mtime": mtime,
                    "size": size,
                    "env": env,
                    "records": db_records
                }

        for r in db_records:
            dedup_key = (r.get("conv_id"), r.get("step_idx"))
            if dedup_key not in seen_steps:
                seen_steps.add(dedup_key)
                all_records.append(r)

    # 清理已在磁盘上删除但缓存中残留的条目
    keys_to_remove = [k for k in cached_files if k not in current_db_keys]
    if keys_to_remove:
        for k in keys_to_remove:
            del cached_files[k]
        cache_modified = True

    # 保存最新增量缓存
    if use_cache and cache_modified:
        cache_data["last_updated"] = time.time()
        save_token_cache(cache_file, cache_data)

    if use_cache and total_dbs > 0:
        if parsed_count == 0:
            print(f"⚡ 增量缓存就绪: 全部 {total_dbs} 个数据库 ({', '.join(summary_parts)}) 均命中缓存，跳过重复解析。")
        else:
            print(
                f"⚡ 增量缓存生效: {cache_hit_count} 个数据库命中缓存，"
                f"{parsed_count} 个有变更/新增重新解析 (总计 {total_dbs} 个: {', '.join(summary_parts)})"
            )
    else:
        print(f"完成扫描与全量解析 {total_dbs} 个数据库文件 ({', '.join(summary_parts)})。")

    print(f"累计提取 {len(all_records)} 条模型调用元数据记录。")
    return all_records


if __name__ == '__main__':
    targets = discover_all_data_dirs()
    print("自动发现的数据目录目标:")
    for t in targets:
        print(f" - [{t['env']}] {t['path']}")
    recs = collect_all_data()
    print("样例记录:", recs[0] if recs else "None")

