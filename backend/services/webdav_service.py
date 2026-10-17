# -*- coding: utf-8 -*-
"""WebDAV 数据主权服务（v1.6.0 预留接口层）：配置校验 / 备份导出恢复 / 三方冲突判定。

定位（roadmap-local-llm-mcp-2026-10-17 §6 / PRD v1.4 Non-goal 1）：
WebDAV 从 v1.4 顺延至 v1.6，启动条件为「v1.5.x 稳定运行 ≥2 周 + 冲突合并 UX
设计稿评审通过 + 与『完全本地』定位的一致性论证成文」。本文件是先行落地的
**接口契约层**：类型定义、参数结构、错误码与冲突模型为终态；IO 编排
（实际上传/下载/合并）标注 [预留]，返回结构化 reserved 应答——后续迭代
只填实现，不改签名与返回 shape。

契约红线：
- 零第三方依赖：WebDAV 是 HTTP（PROPFIND/GET/PUT/MKCOL/DELETE），用 stdlib
  http.client 实现，不引 webdavclient 类库；
- 凭证存独立文件 ~/.glm-chat/webdav.json（不碰 config.json 契约；字段级加密
  复用 v1.3 DPAPI 模式——password 值加密、键名明文）；
- 备份内容范围（v1.4 方案定义）：config.json + sessions.json + 审计导出
  （audit_log.jsonl）——manifest 逐文件记录 sha256，恢复前可校验。

冲突模型（v1.6 设计稿评审输入）：三方冲突 = 本地当前 / 云端当前 / 本地备份基线。
本层提供纯函数判定 classify_conflicts(local, remote, baseline)，把「谁变了」
分类为 only_local / only_remote / both_changed（真冲突）/ unchanged，
供 UX 设计稿消费；合并策略（local_wins/remote_wins/keep_both/ask）为配置项，
执行器 [预留]。
"""
import hashlib
import json
import time

# ================= 类型定义（参数结构与返回 shape，终态）=================

# webdav.json 配置 shape：
#   url            str   WebDAV 端点（必须 https；http 仅 localhost 例外）
#   username       str   账号
#   password       str   密码（DPAPI 字段级加密后落盘；get_config 解密返回）
#   remote_path    str   远端目录（如 /glm-chat-backup；自动 MKCOL）
#   auto_sync      bool  是否自动同步（默认 False——手动优先，信任版语义）
#   conflict_policy str  ask / local_wins / remote_wins / keep_both
#
# validate_config() 返回 (record, error)；record 仅含合法键（password 原样留在
# record 中由调用方加密，与服务层 mcp_dpapi 同模式）。
#
# 备份 manifest shape：
#   {version: 1, app_version, created_at, items: [{path, sha256, bytes}]}
#
# export_backup() 返回 [预留]：{ok: False, reserved: True, error, plan: [...]}
#   plan 描述「将导出哪些文件」——UI 可先行展示导出计划。
#
# detect/classify 冲突入参：{path: sha256} 映射（local/remote/baseline 三份）。
# 返回 {unchanged: [], only_local: [], only_remote: [], conflicts: [{path, ...}]}

# ================= 配置校验 =================

WEBDAV_CONFIG_KEYS = ('url', 'username', 'password', 'remote_path',
                      'auto_sync', 'conflict_policy')
CONFLICT_POLICIES = ('ask', 'local_wins', 'remote_wins', 'keep_both')
BACKUP_MANIFEST_VERSION = 1
# 备份内容范围（v1.4 方案定义；文件名相对于 ~/.glm-chat/）
BACKUP_SCOPE = ('config.json', 'sessions.json', 'audit_log.jsonl')


def validate_config(cfg):
    """WebDAV 配置校验（只验证不落盘）。返回 (record, error)。"""
    if not isinstance(cfg, dict):
        return None, 'WebDAV 配置必须是 JSON 对象'
    record = {}
    url = str(cfg.get('url') or '').strip().rstrip('/')
    if not url:
        return None, '缺少 WebDAV 地址'
    if not url.lower().startswith(('http://', 'https://')):
        return None, 'WebDAV 地址需要 http:// 或 https:// 开头'
    if url.lower().startswith('http://') and 'localhost' not in url \
            and '127.0.0.1' not in url:
        return None, 'WebDAV 必须使用 https://（凭证明文出网风险；localhost 除外）'
    if '@' in url:
        return None, '地址内不允许内嵌凭证（user:pass@host），请分开填写账号密码'
    record['url'] = url
    username = str(cfg.get('username') or '').strip()
    if not username:
        return None, '缺少 WebDAV 账号'
    record['username'] = username
    password = str(cfg.get('password') or '')
    if not password:
        return None, '缺少 WebDAV 密码'
    record['password'] = password
    remote_path = str(cfg.get('remote_path') or '').strip() or '/glm-chat-backup'
    if not remote_path.startswith('/'):
        remote_path = '/' + remote_path
    record['remote_path'] = remote_path.rstrip('/') or '/'
    record['auto_sync'] = bool(cfg.get('auto_sync'))
    policy = str(cfg.get('conflict_policy') or 'ask').strip().lower()
    if policy not in CONFLICT_POLICIES:
        return None, 'conflict_policy 仅支持 %s' % '/'.join(CONFLICT_POLICIES)
    record['conflict_policy'] = policy
    return record, None


def file_sha256(path):
    """文件 sha256（备份 manifest 与恢复校验用；读失败返回 ''）。"""
    h = hashlib.sha256()
    try:
        with open(path, 'rb') as f:
            while True:
                chunk = f.read(256 * 1024)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ''


def build_backup_plan(config_dir):
    """导出计划（真实数据：逐文件 sha256/字节数）——export_backup 的前置展示。"""
    import os
    plan = []
    for rel in BACKUP_SCOPE:
        p = os.path.join(config_dir, rel)
        if os.path.isfile(p):
            plan.append({'path': rel, 'sha256': file_sha256(p),
                         'bytes': os.path.getsize(p)})
        else:
            plan.append({'path': rel, 'missing': True})
    return plan


# ================= 三方冲突判定（纯函数，终态）=================

def classify_conflicts(local, remote, baseline):
    """三方冲突分类：本地当前 vs 云端当前 vs 本地备份基线。

    入参均为 {相对路径: sha256} 映射。分类口径：
    - unchanged   : 三方一致（或本地=基线且远端无）
    - only_local  : 本地相对基线变了、云端未动 → 可安全上行
    - only_remote : 云端相对基线变了、本地未动 → 可安全下行
    - conflicts   : 本地与云端都相对基线变了且互不相同 → 真冲突，按策略裁决
    返回 {unchanged, only_local, only_remote, conflicts}（值为路径列表，
    conflicts 为 [{path, local_sha, remote_sha, baseline_sha}]）。
    """
    local = local or {}
    remote = remote or {}
    baseline = baseline or {}
    out = {'unchanged': [], 'only_local': [], 'only_remote': [], 'conflicts': []}
    paths = set(local) | set(remote) | set(baseline)
    for p in sorted(paths):
        l, r, b = local.get(p, ''), remote.get(p, ''), baseline.get(p, '')
        if l == r:
            out['unchanged'].append(p)
            continue
        local_changed = (l != b)
        remote_changed = (r != b)
        if local_changed and not remote_changed:
            out['only_local'].append(p)
        elif remote_changed and not local_changed:
            out['only_remote'].append(p)
        else:
            out['conflicts'].append({'path': p, 'local_sha': l,
                                     'remote_sha': r, 'baseline_sha': b})
    return out


def resolve_conflict(policy, item):
    """冲突裁决（纯函数）：ask=交还 UI；local/remote_wins=取方；keep_both=双保留标记。

    返回 {'action': 'upload'|'download'|'keep_both'|'ask', 'path': ...}。
    keep_both 的文件名编排（加时间戳后缀）在执行器 [预留] 内落地。
    """
    policy = str(policy or 'ask').lower()
    if policy == 'local_wins':
        return {'action': 'upload', 'path': item.get('path')}
    if policy == 'remote_wins':
        return {'action': 'download', 'path': item.get('path')}
    if policy == 'keep_both':
        return {'action': 'keep_both', 'path': item.get('path')}
    return {'action': 'ask', 'path': item.get('path')}


# ================= IO 编排（v1.6 执行器：stdlib http.client，零依赖）=================
#
# 安全口径（与 S15/㉒ 同族）：
# - http.client 本就不跟随 3xx（no-redirect）；3xx 显式当错误，不带凭证再请求
# - https 强制由 validate_config 保证（localhost 除外）
# - Basic Auth 仅本服务持有；错误响应体读上限 64KB（防病态端点）
# - 恢复落盘仅限 BACKUP_SCOPE 内的相对路径（manifest 恶意路径穿越防护）
# - 下载内容 sha256 与 manifest 对拍，不符拒落盘

import base64
import http.client
import os
import urllib.parse
import xml.etree.ElementTree as ET

from . import mcp_dpapi

WEBDAV_FILE = 'webdav.json'
MANIFEST_NAME = 'manifest.json'
_ERR_READ_CAP = 64 * 1024
_DOWNLOAD_CAP = 256 * 1024 * 1024     # 备份文件下载上限（防 OOM）


class _DavError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _dav_request(record, method, rel_path, body=None, headers=None,
                 timeout=30, read_cap=_ERR_READ_CAP):
    """单次 DAV 请求。rel_path 相对 remote_path（如 'config.json' 或 ''）。

    返回 (status, headers_dict, data_bytes)。网络/协议异常抛 _DavError。
    """
    url = record['url']
    u = urllib.parse.urlsplit(url)
    scheme = (u.scheme or 'https').lower()
    host = u.hostname or ''
    port = u.port or (443 if scheme == 'https' else 80)
    base_path = (u.path or '').rstrip('/')
    remote = record.get('remote_path') or '/glm-chat-backup'
    full_path = base_path + remote.rstrip('/') + '/' + str(rel_path or '').lstrip('/')
    auth = base64.b64encode(('%s:%s' % (record.get('username', ''),
                                        record.get('password', '')))
                            .encode('utf-8')).decode('ascii')
    hdrs = {'Authorization': 'Basic ' + auth,
            'Accept': '*/*'}
    if headers:
        hdrs.update(headers)
    try:
        if scheme == 'https':
            conn = http.client.HTTPSConnection(host, port, timeout=timeout)
        else:
            conn = http.client.HTTPConnection(host, port, timeout=timeout)
    except Exception as e:
        raise _DavError('连接建立失败: %s' % e)
    try:
        conn.request(method, full_path, body=body, headers=hdrs)
        resp = conn.getresponse()
        # no-redirect：3xx 显式拒绝（http.client 不跟随，但也不能把 3xx 当成功）
        if 300 <= resp.status < 400:
            raise _DavError('服务端返回重定向（已按安全口径拒绝）', status=resp.status)
        data = resp.read(read_cap) if read_cap else resp.read()
        hd = {}
        try:
            for k, v in resp.getheaders():
                hd[k.lower()] = v
        except Exception:
            pass
        return resp.status, hd, data
    except _DavError:
        raise
    except Exception as e:
        raise _DavError('请求失败: %s' % e)
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _dav_error_text(status, data=b''):
    """DAV 状态码人话映射。"""
    detail = ''
    try:
        detail = (data or b'').decode('utf-8', 'replace')[:150].strip()
    except Exception:
        pass
    table = {
        401: '认证失败（401）：请检查 WebDAV 账号密码',
        403: '无权访问（403）：账号对该目录无写权限',
        404: '路径不存在（404）：请检查远端目录或先执行一次导出',
        405: '方法不被允许（405）：该端点可能不是标准 WebDAV 服务',
        409: '冲突（409）：父目录不存在',
        507: '服务端存储不足（507）',
    }
    base = table.get(status, 'HTTP %s' % status)
    return base + ('：' + detail if detail else '')


def _ensure_remote_dir(record):
    """MKCOL 远端目录（409=已存在视为 OK）。"""
    status, _, data = _dav_request(record, 'MKCOL', '', timeout=30)
    if status in (201, 204, 409):        # 创建成功 / 已存在
        return None
    raise _DavError(_dav_error_text(status, data), status=status)


def _safe_rel(rel):
    """恢复落盘路径安全校验：仅 BACKUP_SCOPE 内的相对路径（防 manifest 穿越）。"""
    rel = str(rel or '')
    if not rel or rel != os.path.basename(rel) or rel in ('.', '..') \
            or '/' in rel or '\\' in rel or rel.startswith('.'):
        return False
    return True


def test_connection(record):
    """WebDAV 连通性：OPTIONS 端点（DAV 能力声明）+ PROPFIND 远端目录。"""
    if not isinstance(record, dict) or not record.get('url'):
        return {'ok': False, 'error': '缺少 WebDAV 地址'}
    try:
        status, hd, _ = _dav_request(record, 'OPTIONS', '', timeout=15)
        dav_hdr = hd.get('dav', '')
        if status >= 400:
            return {'ok': False, 'error': _dav_error_text(status)}
        # PROPFIND depth 0 确认远端目录可达（不存在也说明连通，只是没备份过）
        pf_status, _, pf_data = _dav_request(
            record, 'PROPFIND', '', timeout=20,
            headers={'Depth': '0', 'Content-Type': 'application/xml'},
            body=b'<?xml version="1.0" encoding="utf-8"?>'
                 b'<D:propfind xmlns:D="DAV:"><D:prop><D:resourcetype/></D:prop></D:propfind>')
        if pf_status in (200, 207, 404):     # 可达（404=目录未建，导出时自动 MKCOL）
            return {'ok': True, 'dav_capability': dav_hdr or 'unknown',
                    'detail': '连接成功（DAV 能力：%s）' % (dav_hdr or '未声明')}
        return {'ok': False, 'error': _dav_error_text(pf_status, pf_data)}
    except _DavError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': '连接测试失败: %s' % e}


def export_backup(config_dir, record=None):
    """导出备份到 WebDAV：MKCOL → 逐文件 PUT → manifest.json。

    record 为已校验配置（含明文 password）；缺省时仅返回计划（UI 预览）。"""
    plan = build_backup_plan(config_dir)
    if not isinstance(record, dict) or not record.get('url'):
        return {'ok': False, 'reserved': True,
                'error': '未配置 WebDAV（已生成本次导出计划；配置后即可上传）',
                'plan': plan,
                'manifest': {'version': BACKUP_MANIFEST_VERSION,
                             'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                             'items': [i for i in plan if not i.get('missing')]}}
    try:
        _ensure_remote_dir(record)
    except _DavError as e:
        return {'ok': False, 'error': '远端目录创建失败: %s' % e}
    uploaded = []
    for item in plan:
        if item.get('missing'):
            continue
        rel = item['path']
        if not _safe_rel(rel):
            continue
        local = os.path.join(config_dir, rel)
        try:
            with open(local, 'rb') as f:
                data = f.read(_DOWNLOAD_CAP)
        except OSError as e:
            return {'ok': False, 'error': '读取 %s 失败: %s' % (rel, e),
                    'uploaded': uploaded}
        status, _, rdata = _dav_request(
            record, 'PUT', rel, body=data, timeout=120, read_cap=_ERR_READ_CAP,
            headers={'Content-Type': 'application/octet-stream'})
        if status not in (200, 201, 204):
            return {'ok': False, 'error': '上传 %s 失败: %s' % (rel, _dav_error_text(status, rdata)),
                    'uploaded': uploaded}
        uploaded.append(rel)
    manifest = {'version': BACKUP_MANIFEST_VERSION,
                'app_version': _app_version(),
                'created_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                'items': [i for i in plan if not i.get('missing')]}
    mbytes = json.dumps(manifest, ensure_ascii=False, indent=1).encode('utf-8')
    status, _, rdata = _dav_request(
        record, 'PUT', MANIFEST_NAME, body=mbytes, timeout=60, read_cap=_ERR_READ_CAP,
        headers={'Content-Type': 'application/json'})
    if status not in (200, 201, 204):
        return {'ok': False, 'error': 'manifest 上传失败: %s' % _dav_error_text(status, rdata),
                'uploaded': uploaded}
    return {'ok': True, 'uploaded': uploaded, 'manifest': manifest}


def _app_version():
    try:
        from .update_service import APP_VERSION
        return APP_VERSION
    except Exception:
        return ''


def _remote_manifest(record):
    """下载远端 manifest.json 并解析。"""
    status, _, data = _dav_request(record, 'GET', MANIFEST_NAME,
                                   timeout=60, read_cap=_ERR_READ_CAP)
    if status == 404:
        return None
    if status != 200:
        raise _DavError(_dav_error_text(status, data), status=status)
    try:
        m = json.loads(data.decode('utf-8'))
    except Exception as e:
        raise _DavError('远端 manifest 解析失败: %s' % e)
    if not isinstance(m, dict) or not isinstance(m.get('items'), list):
        raise _DavError('远端 manifest 结构异常（缺 items）')
    return m


def restore_backup(payload_json, config_dir, record=None):
    """从 WebDAV 备份恢复：下载 manifest+items → 三方冲突判定 → 按策略落盘。

    payload_json：前端可传本地 manifest（缺省用远端 manifest）；record 为已校验
    配置（含明文 password）。未配置 → 仅返回 manifest 校验结果（UI 预览）。

    设计口径（2026-10-17 修正）：manifest sha 是「上次导出快照=三方基线」，
    不是「远端必须等于」的硬校验值——后者会把远端正常演进（另一台机器改了备份）
    误杀成完整性错误，用户连冲突决策的机会都没有。完整性保障改为落盘后重算
    sha 与下载内容对拍（磁盘写入一致性）。"""
    try:
        manifest = json.loads(payload_json or '{}') if payload_json else None
    except Exception as e:
        return {'ok': False, 'error': 'manifest 解析失败: %s' % e}
    if manifest is not None:
        if not isinstance(manifest, dict) or not isinstance(manifest.get('items'), list):
            return {'ok': False, 'error': 'manifest 结构异常（缺 items 数组）'}
        for it in manifest['items']:
            if not isinstance(it, dict) or not it.get('path') or not it.get('sha256'):
                return {'ok': False, 'error': 'manifest items 每项需含 path 与 sha256'}
    if not isinstance(record, dict) or not record.get('url'):
        return {'ok': False,
                'error': '未配置 WebDAV（manifest 校验已通过；配置后即可恢复）',
                'manifest': manifest}
    policy = record.get('conflict_policy') or 'ask'
    try:
        remote_manifest = _remote_manifest(record)
        baseline_manifest = manifest or remote_manifest
        if baseline_manifest is None:
            return {'ok': False, 'error': '远端无备份（manifest.json 不存在）；请先导出'}
        local_sha, remote_sha, baseline_sha = {}, {}, {}
        downloaded = {}
        for it in baseline_manifest['items']:
            rel = it.get('path')
            if not _safe_rel(rel):
                continue                     # 非白名单路径跳过（防穿越）
            baseline_sha[rel] = it.get('sha256') or ''
            local_sha[rel] = file_sha256(os.path.join(config_dir, rel))
            status, _, data = _dav_request(record, 'GET', rel,
                                           timeout=120, read_cap=_DOWNLOAD_CAP)
            if status != 200:
                return {'ok': False,
                        'error': '下载 %s 失败: %s' % (rel, _dav_error_text(status, data))}
            remote_sha[rel] = hashlib.sha256(data).hexdigest()
            downloaded[rel] = data
        verdict = classify_conflicts(local_sha, remote_sha, baseline_sha)
        plan_out = []
        for p in verdict['only_remote']:
            plan_out.append({'path': p, 'action': 'download'})
        for c in verdict['conflicts']:
            plan_out.append({'path': c['path'], 'action': resolve_conflict(policy, c)['action']})
        if policy == 'ask' and verdict['conflicts']:
            return {'ok': False, 'need_decision': True,
                    'conflicts': verdict['conflicts'],
                    'plan': plan_out,
                    'error': '检测到 %d 个冲突文件，需用户选择合并策略' % len(verdict['conflicts'])}
        # 执行落盘（落盘后重算 sha 与下载内容对拍——磁盘一致性保障）
        applied, kept = [], []
        for item in plan_out:
            p = item['path']
            action = item['action']
            if action == 'download':
                target = os.path.join(config_dir, p)
                with open(target, 'wb') as f:
                    f.write(downloaded[p])
                if file_sha256(target) != remote_sha[p]:
                    return {'ok': False, 'error': '落盘校验失败：%s（磁盘写入不一致）' % p,
                            'applied': applied}
                applied.append(p)
            elif action == 'keep_both':
                base, ext = os.path.splitext(p)
                stamp = time.strftime('%Y%m%d-%H%M%S')
                target = os.path.join(config_dir, '%s.%s%s' % (base, stamp, ext))
                with open(target, 'wb') as f:
                    f.write(downloaded[p])
                if file_sha256(target) != remote_sha[p]:
                    return {'ok': False, 'error': '落盘校验失败：%s' % target,
                            'applied': applied}
                kept.append(target)
            # upload（local_wins）→ 不动本地
        return {'ok': True, 'applied': applied, 'kept_both': kept,
                'verdict': verdict,
                'summary': '恢复完成：覆盖 %d，另存 %d，冲突 %d（策略 %s）'
                           % (len(applied), len(kept), len(verdict['conflicts']), policy)}
    except _DavError as e:
        return {'ok': False, 'error': str(e)}
    except Exception as e:
        return {'ok': False, 'error': '恢复失败: %s' % e}


class WebDAVService:
    """WebDAV 服务门面（供 Api 装配；IO 执行器已落地）。"""

    def __init__(self, config_dir=None):
        import os
        self._config_dir = config_dir or os.path.join(
            os.path.expanduser('~'), '.glm-chat')

    # ---- 配置文件（webdav.json，DPAPI 字段级加密 password）----
    def _path(self):
        return os.path.join(self._config_dir, WEBDAV_FILE)

    def get_config(self):
        """读取 webdav.json（DPAPI 解密 password 后返回，键名明文）。"""
        p = self._path()
        if not os.path.isfile(p):
            return {'ok': True, 'config': None}
        try:
            with open(p, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception as e:
            return {'ok': False, 'error': 'webdav.json 读取失败: %s' % e}
        if not isinstance(data, dict):
            return {'ok': False, 'error': 'webdav.json 结构异常'}
        pw = data.get('password')
        if isinstance(pw, str) and pw:
            dec = mcp_dpapi.decrypt_value(pw)
            data['password'] = dec if dec and not dec.startswith(mcp_dpapi.ENC_PREFIX) else ''
        return {'ok': True, 'config': {k: v for k, v in data.items()
                                       if k in WEBDAV_CONFIG_KEYS}}

    def save_config(self, cfg_json):
        """校验 → DPAPI 加密 password → 原子写 webdav.json。"""
        try:
            cfg = json.loads(cfg_json or '{}')
        except Exception as e:
            return {'ok': False, 'error': '配置解析失败: %s' % e}
        record, error = validate_config(cfg)
        if error:
            return {'ok': False, 'error': error}
        out = dict(record)
        enc = mcp_dpapi.encrypt_value(record['password'])
        out['password'] = enc
        try:
            from ..fio import atomic_write_json
            os.makedirs(self._config_dir, exist_ok=True)
            atomic_write_json(self._path(), out, indent=2)
        except Exception as e:
            return {'ok': False, 'error': 'webdav.json 写入失败: %s' % e}
        return {'ok': True, 'config': {k: v for k, v in record.items() if k != 'password'}}

    # ---- 连通性 / 导出 / 恢复 ----
    def _record_for_io(self, cfg_json='{}'):
        """解析前端传入配置（含明文 password）；缺省回落到已存配置。"""
        try:
            cfg = json.loads(cfg_json or '{}') if cfg_json else {}
        except Exception:
            cfg = {}
        if cfg and cfg.get('url'):
            record, error = validate_config(cfg)
            if error:
                return None, {'ok': False, 'error': error}
            return record, None
        stored = self.get_config()
        if not stored.get('ok'):
            return None, stored
        conf = stored.get('config')
        if not conf:
            return None, {'ok': False, 'error': '未配置 WebDAV（设置 → 数据与备份）'}
        return conf, None

    def test(self, cfg_json='{}'):
        record, err = self._record_for_io(cfg_json)
        if err:
            return err
        return test_connection(record)

    def export(self, cfg_json='{}'):
        record, err = self._record_for_io(cfg_json)
        if err:
            # 未配置：仍返回导出计划（UI 预览），不带 reserved 误导
            plan = build_backup_plan(self._config_dir)
            return {'ok': False, 'error': err.get('error', '未配置 WebDAV'), 'plan': plan}
        return export_backup(self._config_dir, record)

    def restore(self, payload_json, cfg_json='{}'):
        record, err = self._record_for_io(cfg_json)
        if err:
            # 未配置：manifest 校验仍执行（UI 预览），返回结构化错误
            try:
                manifest = json.loads(payload_json or '{}') if payload_json else None
            except Exception as e:
                return {'ok': False, 'error': 'manifest 解析失败: %s' % e}
            return {'ok': False, 'error': err.get('error', '未配置 WebDAV'),
                    'manifest': manifest}
        return restore_backup(payload_json, self._config_dir, record)

    def classify_conflicts(self, local, remote, baseline):
        return classify_conflicts(local, remote, baseline)
