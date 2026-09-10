#!/usr/bin/python
# coding: utf-8

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile

if os.path.isdir('/www/server/panel'):
    os.chdir('/www/server/panel')
if os.path.isdir('/www/server/panel/class'):
    sys.path.append('/www/server/panel/class')


class rathole_manager_main:
    PLUGIN_VERSION = '2.1.0'
    BINARY = '/usr/local/bin/rathole'
    CONFIG_DIR = '/etc/rathole'
    CONFIG_FILE = '/etc/rathole/rathole.toml'
    STATE_DIR = '/var/lib/rathole-manager'
    STATE_FILE = '/var/lib/rathole-manager/state.json'
    READY_FILE = '/var/lib/rathole-manager/configured'
    SERVICE = 'rathole'
    RATHOLE_API = 'https://api.github.com/repos/rathole-org/rathole'
    UPDATE_URL = 'https://raw.githubusercontent.com/TianYuYun/Rathole-Bt/main/update.json'
    RAW_ROOT = 'https://raw.githubusercontent.com/TianYuYun/Rathole-Bt'
    PLUGIN_DIR = '/www/server/panel/plugin/rathole_manager'

    def __init__(self):
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        os.makedirs(self.STATE_DIR, exist_ok=True)

    def _ok(self, msg='ok', data=None):
        result = {'status': True, 'msg': msg}
        if data is not None:
            result['data'] = data
        return result

    def _err(self, msg):
        return {'status': False, 'msg': str(msg)}

    def _arg(self, args, name, default=''):
        value = getattr(args, name, default)
        return default if value is None else value

    def _run(self, cmd, timeout=20):
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout.strip()

    def _http_json(self, url):
        req = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'Rathole-Bt/%s' % self.PLUGIN_VERSION,
        })
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))

    def _read_state(self):
        base = {'mode': 'client', 'services': [], 'transport': 'noise', 'channel': 'stable'}
        if not os.path.isfile(self.STATE_FILE):
            return base
        try:
            with open(self.STATE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            pass
        return base

    def _write_state(self, data):
        tmp = self.STATE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.STATE_FILE)

    @staticmethod
    def _escape(value):
        return str(value).replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def _valid_host(host):
        host = str(host or '').strip()
        return bool(host) and len(host) <= 253 and not re.search(r'\s|/|\\', host)

    @staticmethod
    def _port(value, label='端口'):
        try:
            port = int(str(value).strip())
        except Exception:
            raise ValueError('%s必须是数字' % label)
        if port < 1 or port > 65535:
            raise ValueError('%s必须在 1-65535 之间' % label)
        return port

    def _addr(self, host, port, host_label='地址', port_label='端口'):
        host = str(host or '').strip()
        if not self._valid_host(host):
            raise ValueError('%s无效' % host_label)
        port = self._port(port, port_label)
        if ':' in host and not host.startswith('['):
            host = '[%s]' % host
        return '%s:%d' % (host, port)

    @staticmethod
    def _split_addr(value, default_host='', default_port=''):
        value = str(value or '').strip()
        m = re.fullmatch(r'\[([^\]]+)\]:(\d{1,5})', value)
        if m:
            return m.group(1), m.group(2)
        m = re.fullmatch(r'(.+):(\d{1,5})', value)
        if m:
            return m.group(1), m.group(2)
        return default_host, str(default_port)

    @staticmethod
    def _valid_key(value):
        return bool(re.fullmatch(r'[A-Za-z0-9+/]{42,44}={0,2}', str(value or '').strip()))

    def _normalize_services(self, raw, mode):
        try:
            rows = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            raise ValueError('穿透规则数据格式错误')
        if not isinstance(rows, list) or not rows:
            raise ValueError('至少需要一条穿透规则')
        if len(rows) > 128:
            raise ValueError('最多支持 128 条规则')
        result, names = [], set()
        for row in rows:
            name = str(row.get('name', '')).strip()
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
                raise ValueError('规则名称仅允许字母、数字、下划线和短横线')
            if name in names:
                raise ValueError('规则名称重复：%s' % name)
            names.add(name)
            proto = str(row.get('type', 'tcp')).lower()
            if proto not in ('tcp', 'udp'):
                raise ValueError('规则 %s 的协议无效' % name)
            token = str(row.get('token', '')).strip()
            if len(token) < 8:
                raise ValueError('规则 %s 的 Token 至少 8 个字符' % name)
            item = {'name': name, 'type': proto, 'token': token}
            if mode == 'client':
                item['local_addr'] = self._addr(row.get('host', '127.0.0.1'), row.get('port', '80'),
                                                '本地服务地址', '本地服务端口')
            else:
                item['bind_addr'] = self._addr(row.get('host', '127.0.0.1'), row.get('port', '18080'),
                                               '公网机转发地址', '公网机转发端口')
            result.append(item)
        return result

    def _render_config(self, mode, base_addr, services, transport, noise_key):
        lines = ['# Generated by Rathole-Bt. Do not edit while panel management is enabled.', '']
        if mode == 'server':
            lines += ['[server]', 'bind_addr = "%s"' % self._escape(base_addr),
                      'heartbeat_interval = 30', '', '[server.transport]',
                      'type = "%s"' % transport, '']
            if transport == 'noise':
                lines += ['[server.transport.noise]',
                          'local_private_key = "%s"' % self._escape(noise_key), '']
            for s in services:
                lines += ['[server.services.%s]' % s['name'], 'type = "%s"' % s['type'],
                          'token = "%s"' % self._escape(s['token']),
                          'bind_addr = "%s"' % self._escape(s['bind_addr']), '']
        else:
            lines += ['[client]', 'remote_addr = "%s"' % self._escape(base_addr),
                      'heartbeat_timeout = 40', 'retry_interval = 1', '',
                      '[client.transport]', 'type = "%s"' % transport, '']
            if transport == 'noise':
                lines += ['[client.transport.noise]',
                          'remote_public_key = "%s"' % self._escape(noise_key), '']
            for s in services:
                lines += ['[client.services.%s]' % s['name'], 'type = "%s"' % s['type'],
                          'token = "%s"' % self._escape(s['token']),
                          'local_addr = "%s"' % self._escape(s['local_addr']), '']
        return '\n'.join(lines)

    def _binary_version(self):
        if not os.path.isfile(self.BINARY):
            return ''
        rc, out = self._run([self.BINARY, '--version'], 5)
        if rc != 0:
            return ''
        m = re.search(r'Build Version:\s*([^\s]+)', out, re.I)
        return m.group(1) if m else (out.splitlines()[0] if out else '')

    def _asset(self, release):
        machine = platform.machine().lower()
        targets = ['x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-musl'] if machine in ('x86_64', 'amd64') else \
                  ['aarch64-unknown-linux-musl', 'aarch64-unknown-linux-gnu'] if machine in ('aarch64', 'arm64') else []
        if not targets:
            raise RuntimeError('暂不支持自动安装的 CPU 架构：%s' % machine)
        for target in targets:
            for asset in release.get('assets', []):
                name = asset.get('name', '').lower()
                if target in name and name.endswith('.zip'):
                    return asset.get('name'), asset.get('browser_download_url')
        raise RuntimeError('官方 Release 中没有适合当前架构的安装包')

    def _gen_noise(self):
        if not os.path.isfile(self.BINARY):
            raise RuntimeError('请先安装 Rathole 核心')
        rc, out = self._run([self.BINARY, '--genkey'], 10)
        if rc != 0:
            raise RuntimeError(out or '生成 Noise 密钥失败')
        priv = re.search(r'Private Key:\s*([A-Za-z0-9+/=]+)', out, re.I)
        pub = re.search(r'Public Key:\s*([A-Za-z0-9+/=]+)', out, re.I)
        if not priv or not pub:
            raise RuntimeError('无法解析 Rathole 密钥输出')
        return priv.group(1), pub.group(1)

    def get_status(self, args):
        state = self._read_state()
        installed = os.path.isfile(self.BINARY) and os.access(self.BINARY, os.X_OK)
        active = self._run(['systemctl', 'is-active', '--quiet', self.SERVICE], 5)[0] == 0
        enabled = self._run(['systemctl', 'is-enabled', '--quiet', self.SERVICE], 5)[0] == 0
        return self._ok('状态获取成功', {
            'installed': installed, 'active': active, 'enabled': enabled,
            'configured': os.path.isfile(self.READY_FILE), 'version': self._binary_version(),
            'plugin_version': self.PLUGIN_VERSION, 'mode': state.get('mode', 'client'),
            'arch': platform.machine()
        })

    def get_release_info(self, args):
        try:
            stable = self._http_json(self.RATHOLE_API + '/releases/latest')
            return self._ok('版本信息获取成功', {
                'stable': stable.get('tag_name', ''), 'current': self._binary_version()
            })
        except Exception as exc:
            return self._err('获取 Rathole 版本信息失败：%s' % exc)

    def install_core(self, args):
        try:
            release = self._http_json(self.RATHOLE_API + '/releases/latest')
            asset_name, url = self._asset(release)
            with tempfile.TemporaryDirectory(prefix='rathole-core-') as tmp:
                archive = os.path.join(tmp, asset_name)
                req = urllib.request.Request(url, headers={'User-Agent': 'Rathole-Bt/%s' % self.PLUGIN_VERSION})
                with urllib.request.urlopen(req, timeout=90) as response, open(archive, 'wb') as f:
                    shutil.copyfileobj(response, f)
                with zipfile.ZipFile(archive) as zf:
                    names = [n for n in zf.namelist() if os.path.basename(n) == 'rathole']
                    if not names:
                        raise RuntimeError('官方压缩包中没有 rathole 可执行文件')
                    zf.extract(names[0], tmp)
                    shutil.copy2(os.path.join(tmp, names[0]), self.BINARY)
                    os.chmod(self.BINARY, 0o755)
            return self._ok('Rathole 已安装/升级：%s' % self._binary_version())
        except Exception as exc:
            return self._err('安装失败：%s' % exc)

    def get_config(self, args):
        state = self._read_state()
        mode = state.get('mode', 'client')
        base_host, base_port = self._split_addr(state.get('base_addr', ''),
                                                 '0.0.0.0' if mode == 'server' else '', '2333')
        rows = []
        for s in state.get('services', []):
            item = {'name': s.get('name', ''), 'type': s.get('type', 'tcp'), 'token': s.get('token', '')}
            addr = s.get('local_addr', '') if mode == 'client' else s.get('bind_addr', '')
            host, port = self._split_addr(addr, '127.0.0.1', '80' if mode == 'client' else '18080')
            item.update({'host': host, 'port': port})
            rows.append(item)
        return self._ok('配置获取成功', {
            'mode': mode, 'base_host': base_host, 'base_port': base_port,
            'transport': state.get('transport', 'noise'), 'services': rows,
            'noise_public_key': state.get('noise_public_key', ''),
            'noise_remote_public_key': state.get('noise_remote_public_key', '')
        })

    def save_config(self, args):
        try:
            mode = str(self._arg(args, 'mode', 'client')).lower()
            if mode not in ('client', 'server'):
                raise ValueError('运行模式无效')
            host = str(self._arg(args, 'base_host', '')).strip()
            port = self._arg(args, 'base_port', '')
            base_addr = self._addr(host, port,
                                   '公网服务器地址' if mode == 'client' else '监听地址', '隧道端口')
            services = self._normalize_services(self._arg(args, 'services', '[]'), mode)
            transport = str(self._arg(args, 'transport', 'noise')).lower()
            if transport not in ('tcp', 'noise'):
                raise ValueError('加密方式无效')
            state = self._read_state()
            noise_key = ''
            if transport == 'noise':
                if mode == 'server':
                    private = state.get('noise_private_key', '')
                    public = state.get('noise_public_key', '')
                    if not self._valid_key(private) or not self._valid_key(public):
                        private, public = self._gen_noise()
                        state['noise_private_key'], state['noise_public_key'] = private, public
                    noise_key = private
                else:
                    noise_key = str(self._arg(args, 'noise_remote_public_key', '')).strip()
                    if not self._valid_key(noise_key):
                        raise ValueError('请输入服务端 Noise 公钥')
                    state['noise_remote_public_key'] = noise_key
            text = self._render_config(mode, base_addr, services, transport, noise_key)
            if os.path.isfile(self.CONFIG_FILE):
                shutil.copy2(self.CONFIG_FILE, self.CONFIG_FILE + '.bak')
            tmp = self.CONFIG_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                f.write(text)
            os.chmod(tmp, 0o640)
            try:
                shutil.chown(tmp, user='root', group='rathole')
            except Exception:
                pass
            os.replace(tmp, self.CONFIG_FILE)
            state.update({'mode': mode, 'base_addr': base_addr, 'services': services, 'transport': transport})
            self._write_state(state)
            with open(self.READY_FILE, 'w', encoding='utf-8') as f:
                f.write('configured\n')
            os.chmod(self.READY_FILE, 0o600)
            return self._ok('配置已保存', {'noise_public_key': state.get('noise_public_key', '')})
        except Exception as exc:
            return self._err(exc)

    def generate_noise_keypair(self, args):
        try:
            private, public = self._gen_noise()
            state = self._read_state()
            state['noise_private_key'], state['noise_public_key'] = private, public
            self._write_state(state)
            return self._ok('Noise 密钥已生成', {'public_key': public})
        except Exception as exc:
            return self._err(exc)

    def validate_config(self, args):
        if not os.path.isfile(self.BINARY):
            return self._err('请先安装 Rathole 核心')
        if not os.path.isfile(self.READY_FILE) or not os.path.isfile(self.CONFIG_FILE):
            return self._err('尚未保存有效配置')
        text = open(self.CONFIG_FILE, 'r', encoding='utf-8', errors='replace').read(65536)
        state = self._read_state()
        expected = '[server]' if state.get('mode') == 'server' else '[client]'
        if expected not in text:
            return self._err('配置文件缺少 %s' % expected)
        return self._ok('配置检查通过')

    def service_action(self, args):
        cmd = str(self._arg(args, 'cmd', '')).lower()
        if cmd not in ('start', 'stop', 'restart', 'enable', 'disable'):
            return self._err('不支持的服务操作')
        if cmd in ('start', 'restart'):
            check = self.validate_config(args)
            if not check.get('status'):
                return self._err('不能启动：%s' % check.get('msg'))
        rc, out = self._run(['systemctl', cmd, self.SERVICE], 20)
        if rc != 0:
            return self._err(out or 'systemctl 操作失败')
        if cmd in ('start', 'restart') and self._run(['systemctl', 'is-active', '--quiet', self.SERVICE], 5)[0] != 0:
            _, logs = self._run(['journalctl', '-u', self.SERVICE, '-n', '12', '--no-pager', '-o', 'cat'], 8)
            return self._err('Rathole 启动失败：%s' % (logs or '请查看日志'))
        return self._ok('操作完成')

    def get_logs(self, args):
        try:
            lines = max(20, min(int(self._arg(args, 'lines', 200)), 500))
        except Exception:
            lines = 200
        rc, out = self._run(['journalctl', '-u', self.SERVICE, '-n', str(lines), '--no-pager', '-o', 'short-iso'], 10)
        return self._ok('日志读取成功', {'log': out}) if rc == 0 else self._err(out or '读取日志失败')

    @staticmethod
    def _version(value):
        nums = re.findall(r'\d+', str(value or ''))
        return tuple(int(x) for x in (nums + ['0', '0', '0'])[:3])

    def get_plugin_update(self, args):
        try:
            meta = self._http_json(self.UPDATE_URL)
            latest = str(meta.get('version', '')).strip()
            if not latest:
                raise RuntimeError('更新清单缺少版本号')
            return self._ok('插件版本检查完成', {
                'current': self.PLUGIN_VERSION, 'latest': latest,
                'has_update': self._version(latest) > self._version(self.PLUGIN_VERSION),
                'changelog': meta.get('changelog', []), 'published_at': meta.get('published_at', '')
            })
        except Exception as exc:
            return self._err('检查插件更新失败：%s' % exc)

    def install_plugin_update(self, args):
        try:
            meta = self._http_json(self.UPDATE_URL)
            latest = str(meta.get('version', '')).strip()
            if self._version(latest) <= self._version(self.PLUGIN_VERSION):
                return self._ok('当前已是最新版本：%s' % self.PLUGIN_VERSION)
            tag = str(meta.get('tag', 'v' + latest)).strip()
            files = meta.get('files', [])
            allowed = {'index.html', 'rathole_manager_main.py', 'install.sh', 'info.json',
                       'README.md', 'CHANGELOG.md'}
            if not files or any(name not in allowed for name in files):
                raise RuntimeError('更新清单文件列表无效')
            backup = os.path.join(self.STATE_DIR, 'plugin-backup-' + self.PLUGIN_VERSION)
            os.makedirs(backup, exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='rathole-plugin-update-') as tmp:
                for name in files:
                    url = '%s/%s/%s' % (self.RAW_ROOT, tag, name)
                    req = urllib.request.Request(url, headers={'User-Agent': 'Rathole-Bt/%s' % self.PLUGIN_VERSION})
                    with urllib.request.urlopen(req, timeout=30) as response, open(os.path.join(tmp, name), 'wb') as f:
                        shutil.copyfileobj(response, f)
                py = os.path.join(tmp, 'rathole_manager_main.py')
                if os.path.isfile(py):
                    rc, out = self._run([sys.executable, '-m', 'py_compile', py], 15)
                    if rc != 0:
                        raise RuntimeError('新版 Python 检查失败：%s' % out)
                for name in files:
                    dst = os.path.join(self.PLUGIN_DIR, name)
                    if os.path.isfile(dst):
                        shutil.copy2(dst, os.path.join(backup, name))
                    tmp_dst = dst + '.update-tmp'
                    shutil.copy2(os.path.join(tmp, name), tmp_dst)
                    os.replace(tmp_dst, dst)
                    if name in ('rathole_manager_main.py', 'install.sh'):
                        os.chmod(dst, 0o755)
            return self._ok('插件已更新到 %s，请关闭并重新打开插件窗口' % latest)
        except Exception as exc:
            return self._err('插件更新失败：%s' % exc)
