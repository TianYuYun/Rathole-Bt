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
try:
    import public  # noqa: F401
except Exception:
    public = None


class rathole_manager_main:
    PLUGIN_VERSION = '1.0.1'
    BINARY = '/usr/local/bin/rathole'
    CONFIG_DIR = '/etc/rathole'
    CONFIG_FILE = '/etc/rathole/rathole.toml'
    STATE_DIR = '/var/lib/rathole-manager'
    STATE_FILE = '/var/lib/rathole-manager/state.json'
    READY_FILE = '/var/lib/rathole-manager/configured'
    SERVICE = 'rathole'
    GITHUB_API = 'https://api.github.com/repos/rathole-org/rathole'
    PLUGIN_API = 'https://api.github.com/repos/TianYuYun/Rathole-Bt'
    PLUGIN_DIR = '/www/server/panel/plugin/rathole_manager'

    def __init__(self):
        os.makedirs(self.CONFIG_DIR, exist_ok=True)
        os.makedirs(self.STATE_DIR, exist_ok=True)
        try:
            os.chmod(self.CONFIG_DIR, 0o750)
            os.chmod(self.STATE_DIR, 0o700)
        except Exception:
            pass

    # ---------- generic helpers ----------
    def _ok(self, msg='ok', data=None):
        out = {'status': True, 'msg': msg}
        if data is not None:
            out['data'] = data
        return out

    def _err(self, msg):
        return {'status': False, 'msg': str(msg)}

    def _arg(self, args, name, default=''):
        value = getattr(args, name, default)
        return default if value is None else value

    def _run(self, cmd, timeout=20):
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            check=False,
        )
        return proc.returncode, proc.stdout.strip()

    def _read_state(self):
        base = {'mode': 'client', 'channel': 'stable', 'services': [], 'transport': 'noise'}
        if not os.path.exists(self.STATE_FILE):
            return base
        try:
            with open(self.STATE_FILE, 'r', encoding='utf-8') as handle:
                data = json.load(handle)
            if isinstance(data, dict):
                base.update(data)
        except Exception:
            pass
        return base

    def _write_state(self, data):
        os.makedirs(self.STATE_DIR, exist_ok=True)
        tmp = self.STATE_FILE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.STATE_FILE)

    @staticmethod
    def _toml_escape(value):
        return str(value).replace('\\', '\\\\').replace('"', '\\"')

    @staticmethod
    def _valid_service_name(name):
        return bool(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name or ''))

    @staticmethod
    def _valid_host(host):
        host = (host or '').strip()
        if not host or len(host) > 253 or re.search(r'\s', host):
            return False
        # IPv4/hostname/IPv6 are accepted. Port must be supplied separately.
        return '/' not in host and '\\' not in host

    @staticmethod
    def _valid_port(value, field_name='端口'):
        try:
            port = int(str(value).strip())
        except Exception:
            raise ValueError('%s 必须是 1-65535 的数字' % field_name)
        if port < 1 or port > 65535:
            raise ValueError('%s 必须在 1-65535 之间' % field_name)
        return port

    def _join_addr(self, host, port, host_label='地址', port_label='端口'):
        host = (host or '').strip()
        if not self._valid_host(host):
            raise ValueError('%s无效' % host_label)
        port = self._valid_port(port, port_label)
        if ':' in host and not (host.startswith('[') and host.endswith(']')):
            host = '[%s]' % host
        return '%s:%d' % (host, port)

    @staticmethod
    def _split_addr(value, default_host='', default_port=''):
        value = (value or '').strip()
        if not value:
            return default_host, str(default_port or '')
        if value.startswith('['):
            match = re.fullmatch(r'\[([^\]]+)\]:(\d{1,5})', value)
            if match:
                return match.group(1), match.group(2)
        match = re.fullmatch(r'(.+):(\d{1,5})', value)
        if match:
            return match.group(1), match.group(2)
        return default_host, str(default_port or '')

    @staticmethod
    def _valid_noise_key(key):
        return bool(re.fullmatch(r'[A-Za-z0-9+/]{42,44}={0,2}', (key or '').strip()))

    def _parse_services_input(self, raw):
        try:
            services = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            raise ValueError('穿透规则数据格式错误')
        if not isinstance(services, list) or not services:
            raise ValueError('至少需要一条穿透规则')
        if len(services) > 128:
            raise ValueError('单个配置最多支持 128 条规则')
        return services

    def _normalize_services(self, raw, mode):
        services = self._parse_services_input(raw)
        result = []
        seen = set()
        for item in services:
            if not isinstance(item, dict):
                raise ValueError('穿透规则格式错误')
            name = str(item.get('name', '')).strip()
            if not self._valid_service_name(name):
                raise ValueError('规则名称仅允许字母、数字、下划线和短横线，长度 1-64')
            if name in seen:
                raise ValueError('规则名称重复：%s' % name)
            seen.add(name)

            proto = str(item.get('type', 'tcp')).strip().lower()
            if proto not in ('tcp', 'udp'):
                raise ValueError('规则 %s 仅支持 TCP 或 UDP' % name)

            token = str(item.get('token', '')).strip()
            if len(token) < 8:
                raise ValueError('规则 %s 的 Token 至少 8 个字符' % name)
            if len(token) > 512:
                raise ValueError('规则 %s 的 Token 过长' % name)

            row = {'name': name, 'type': proto, 'token': token}
            if mode == 'client':
                legacy_host, legacy_port = self._split_addr(item.get('local_addr', ''), '127.0.0.1', '80')
                host = str(item.get('local_host', legacy_host)).strip()
                port = item.get('local_port', legacy_port)
                row['local_addr'] = self._join_addr(host, port, '本地服务地址', '本地服务端口')
            else:
                legacy_host, legacy_port = self._split_addr(item.get('bind_addr', ''), '127.0.0.1', '18080')
                host = str(item.get('bind_host', legacy_host)).strip()
                port = item.get('bind_port', legacy_port)
                row['bind_addr'] = self._join_addr(host, port, '公网暴露地址', '公网暴露端口')
            result.append(row)
        return result

    def _render_config(self, mode, base_addr, services, transport='noise', noise_key=''):
        lines = ['# Generated by BT Rathole Manager.', '# Edit from the BT panel to keep state synchronized.', '']
        if mode == 'server':
            lines += [
                '[server]',
                'bind_addr = "%s"' % self._toml_escape(base_addr),
                'heartbeat_interval = 30',
                '',
                '[server.transport]',
                'type = "%s"' % transport,
                '',
            ]
            if transport == 'noise':
                lines += [
                    '[server.transport.noise]',
                    'local_private_key = "%s"' % self._toml_escape(noise_key),
                    '',
                ]
            for service in services:
                lines += [
                    '[server.services.%s]' % service['name'],
                    'type = "%s"' % service['type'],
                    'token = "%s"' % self._toml_escape(service['token']),
                    'bind_addr = "%s"' % self._toml_escape(service['bind_addr']),
                    '',
                ]
        else:
            lines += [
                '[client]',
                'remote_addr = "%s"' % self._toml_escape(base_addr),
                'heartbeat_timeout = 40',
                'retry_interval = 1',
                '',
                '[client.transport]',
                'type = "%s"' % transport,
                '',
            ]
            if transport == 'noise':
                lines += [
                    '[client.transport.noise]',
                    'remote_public_key = "%s"' % self._toml_escape(noise_key),
                    '',
                ]
            for service in services:
                lines += [
                    '[client.services.%s]' % service['name'],
                    'type = "%s"' % service['type'],
                    'token = "%s"' % self._toml_escape(service['token']),
                    'local_addr = "%s"' % self._toml_escape(service['local_addr']),
                    '',
                ]
        return '\n'.join(lines)

    def _binary_version(self):
        if not os.path.isfile(self.BINARY):
            return ''
        rc, out = self._run([self.BINARY, '--version'], timeout=5)
        if rc != 0:
            return ''
        match = re.search(r'Build Version:\s*([^\s]+)', out, re.I)
        if match:
            return match.group(1)
        return out.splitlines()[0].strip() if out else ''

    def _github_json(self, url):
        req = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'BT-Rathole-Manager/%s' % self.PLUGIN_VERSION,
        })
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode('utf-8'))

    def _asset_for_arch(self, release):
        machine = platform.machine().lower()
        assets = [(a.get('name', ''), a.get('browser_download_url', '')) for a in release.get('assets', [])]
        if machine in ('x86_64', 'amd64'):
            preferred = ['x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-musl']
        elif machine in ('aarch64', 'arm64'):
            preferred = ['aarch64-unknown-linux-musl', 'aarch64-unknown-linux-gnu']
        else:
            raise RuntimeError('暂不支持自动安装的 CPU 架构：%s' % machine)
        for target in preferred:
            for name, url in assets:
                low = name.lower()
                if target in low and low.endswith('.zip'):
                    return name, url
        raise RuntimeError('官方 Release 中未找到适合 %s 的 Linux 安装包' % machine)

    def _generate_noise_keys(self):
        if not os.path.isfile(self.BINARY):
            raise RuntimeError('请先安装 Rathole 核心')
        rc, out = self._run([self.BINARY, '--genkey'], timeout=10)
        if rc != 0:
            raise RuntimeError(out or '生成 Noise 密钥失败')
        priv = re.search(r'Private Key:\s*([A-Za-z0-9+/=]+)', out, re.I)
        pub = re.search(r'Public Key:\s*([A-Za-z0-9+/=]+)', out, re.I)
        if not priv or not pub:
            raise RuntimeError('无法解析 Rathole --genkey 输出')
        if not self._valid_noise_key(priv.group(1)) or not self._valid_noise_key(pub.group(1)):
            raise RuntimeError('Rathole 返回的 Noise 密钥格式无效')
        return priv.group(1), pub.group(1)

    def _validate_saved_state(self):
        state = self._read_state()
        mode = state.get('mode', '')
        if mode not in ('server', 'client'):
            raise ValueError('尚未保存有效的运行模式')
        base_addr = state.get('base_addr', '')
        host, port = self._split_addr(base_addr)
        if not host or not port:
            raise ValueError('尚未保存有效的连接地址')
        self._join_addr(host, port, '连接地址', '连接端口')
        self._normalize_services(state.get('services', []), mode)
        transport = state.get('transport', 'noise')
        if transport not in ('tcp', 'noise'):
            raise ValueError('加密方式无效')
        if transport == 'noise':
            key = state.get('noise_private_key', '') if mode == 'server' else state.get('noise_remote_public_key', '')
            if not self._valid_noise_key(key):
                raise ValueError('Noise 密钥无效')
        if not os.path.isfile(self.CONFIG_FILE):
            raise ValueError('配置文件不存在')
        with open(self.CONFIG_FILE, 'r', encoding='utf-8', errors='replace') as handle:
            config_text = handle.read(65536)
        expected = '[server]' if mode == 'server' else '[client]'
        if expected not in config_text:
            raise ValueError('配置文件缺少 %s 段，请重新保存配置' % expected)
        return state

    # ---------- panel APIs ----------
    def get_status(self, args):
        state = self._read_state()
        installed = os.path.isfile(self.BINARY) and os.access(self.BINARY, os.X_OK)
        active = False
        enabled = False
        if shutil.which('systemctl'):
            active = self._run(['systemctl', 'is-active', '--quiet', self.SERVICE], timeout=5)[0] == 0
            enabled = self._run(['systemctl', 'is-enabled', '--quiet', self.SERVICE], timeout=5)[0] == 0
        configured = os.path.exists(self.READY_FILE)
        return self._ok('状态获取成功', {
            'installed': installed,
            'version': self._binary_version(),
            'active': active,
            'enabled': enabled,
            'configured': configured,
            'mode': state.get('mode', 'client'),
            'channel': state.get('channel', 'stable'),
            'arch': platform.machine(),
            'plugin_version': self.PLUGIN_VERSION,
        })

    def get_release_info(self, args):
        try:
            stable = self._github_json(self.GITHUB_API + '/releases/latest')
            return self._ok('版本信息获取成功', {
                'stable': stable.get('tag_name', ''),
                'current': self._binary_version(),
                'plugin_version': self.PLUGIN_VERSION,
            })
        except Exception as exc:
            return self._err('获取 Rathole 官方版本信息失败：%s' % exc)

    def uninstall_core(self, args):
        try:
            self._run(['systemctl', 'stop', self.SERVICE], timeout=10)
            if os.path.isfile(self.BINARY):
                os.remove(self.BINARY)
            if os.path.exists(self.READY_FILE):
                os.remove(self.READY_FILE)
            state = self._read_state()
            state['release_tag'] = ''
            self._write_state(state)
            return self._ok('Rathole 核心已卸载，/etc/rathole 配置保留未删除')
        except Exception as exc:
            return self._err('卸载失败：%s' % exc)

    def install_core(self, args):
        channel = str(self._arg(args, 'channel', 'stable')).strip().lower()
        if channel not in ('stable', 'dev'):
            return self._err('版本通道仅允许 stable 或 dev')
        was_active = self._run(['systemctl', 'is-active', '--quiet', self.SERVICE], timeout=5)[0] == 0
        try:
            release_url = self.GITHUB_API + ('/releases/latest' if channel == 'stable' else '/releases/tags/dev-latest')
            release = self._github_json(release_url)
            asset_name, download_url = self._asset_for_arch(release)
            with tempfile.TemporaryDirectory(prefix='rathole-install-') as temp_dir:
                archive_path = os.path.join(temp_dir, asset_name)
                request = urllib.request.Request(download_url, headers={'User-Agent': 'BT-Rathole-Manager/%s' % self.PLUGIN_VERSION})
                with urllib.request.urlopen(request, timeout=90) as response, open(archive_path, 'wb') as output:
                    shutil.copyfileobj(response, output)
                with zipfile.ZipFile(archive_path, 'r') as archive:
                    candidates = [name for name in archive.namelist() if os.path.basename(name) == 'rathole']
                    if not candidates:
                        raise RuntimeError('官方压缩包中没有找到 rathole 可执行文件')
                    archive.extract(candidates[0], temp_dir)
                    source = os.path.join(temp_dir, candidates[0])
                    shutil.copy2(source, self.BINARY)
                    os.chmod(self.BINARY, 0o755)
            state = self._read_state()
            state['channel'] = channel
            state['release_tag'] = release.get('tag_name', '')
            self._write_state(state)
            if was_active and os.path.exists(self.READY_FILE):
                self._run(['systemctl', 'restart', self.SERVICE], timeout=20)
            return self._ok('Rathole 已安装/升级：%s' % self._binary_version())
        except Exception as exc:
            return self._err('安装失败：%s' % exc)

    def get_config(self, args):
        state = self._read_state()
        mode = state.get('mode', 'client')
        default_host = '0.0.0.0' if mode == 'server' else ''
        default_port = '2333'
        base_host, base_port = self._split_addr(state.get('base_addr', ''), default_host, default_port)
        services = []
        for item in state.get('services', []) if isinstance(state.get('services', []), list) else []:
            row = dict(item)
            if mode == 'client':
                host, port = self._split_addr(item.get('local_addr', ''), '127.0.0.1', '80')
                row['local_host'] = host
                row['local_port'] = port
            else:
                host, port = self._split_addr(item.get('bind_addr', ''), '127.0.0.1', '18080')
                row['bind_host'] = host
                row['bind_port'] = port
            services.append(row)
        return self._ok('配置获取成功', {
            'mode': mode,
            'base_host': base_host,
            'base_port': base_port,
            'services': services,
            'transport': state.get('transport', 'noise'),
            'noise_public_key': state.get('noise_public_key', ''),
            'noise_remote_public_key': state.get('noise_remote_public_key', ''),
        })

    def save_config(self, args):
        mode = str(self._arg(args, 'mode', 'client')).strip().lower()
        if mode not in ('server', 'client'):
            return self._err('请选择客户端或服务端模式')
        try:
            base_host = str(self._arg(args, 'base_host', '')).strip()
            base_port = self._arg(args, 'base_port', '')
            if not base_host:
                # V1 compatibility for callers still posting base_addr.
                base_host, base_port = self._split_addr(str(self._arg(args, 'base_addr', '')).strip())
            if mode == 'server':
                base_addr = self._join_addr(base_host, base_port, '监听地址', '隧道端口')
            else:
                base_addr = self._join_addr(base_host, base_port, '公网服务器地址', '隧道端口')

            services = self._normalize_services(self._arg(args, 'services', '[]'), mode)
            transport = str(self._arg(args, 'transport', 'noise')).strip().lower()
            if transport not in ('tcp', 'noise'):
                raise ValueError('通道加密仅支持 Noise 或 TCP')

            state = self._read_state()
            noise_key = ''
            if transport == 'noise':
                if mode == 'server':
                    private_key = state.get('noise_private_key', '')
                    public_key = state.get('noise_public_key', '')
                    if not self._valid_noise_key(private_key) or not self._valid_noise_key(public_key):
                        private_key, public_key = self._generate_noise_keys()
                        state['noise_private_key'] = private_key
                        state['noise_public_key'] = public_key
                    noise_key = private_key
                else:
                    noise_key = str(self._arg(args, 'noise_remote_public_key', '')).strip()
                    if not self._valid_noise_key(noise_key):
                        raise ValueError('请输入公网服务端生成的 Noise 公钥')

            config_text = self._render_config(mode, base_addr, services, transport, noise_key)
            if os.path.exists(self.CONFIG_FILE):
                shutil.copy2(self.CONFIG_FILE, self.CONFIG_FILE + '.bak')
            tmp = self.CONFIG_FILE + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as handle:
                handle.write(config_text)
            os.chmod(tmp, 0o640)
            try:
                shutil.chown(tmp, user='root', group='rathole')
            except Exception:
                pass
            os.replace(tmp, self.CONFIG_FILE)

            state.update({
                'mode': mode,
                'base_addr': base_addr,
                'services': services,
                'transport': transport,
            })
            if mode == 'client':
                state['noise_remote_public_key'] = noise_key if transport == 'noise' else ''
            self._write_state(state)
            with open(self.READY_FILE, 'w', encoding='utf-8') as handle:
                handle.write('configured\n')
            os.chmod(self.READY_FILE, 0o600)
            return self._ok('配置已保存，可以启动 Rathole', {
                'noise_public_key': state.get('noise_public_key', '') if mode == 'server' else ''
            })
        except Exception as exc:
            return self._err(exc)

    def generate_noise_keypair(self, args):
        try:
            private_key, public_key = self._generate_noise_keys()
            state = self._read_state()
            state['noise_private_key'] = private_key
            state['noise_public_key'] = public_key
            self._write_state(state)
            return self._ok('Noise 密钥已生成，只把公钥提供给客户端', {'public_key': public_key})
        except Exception as exc:
            return self._err(exc)

    def test_connectivity(self, args):
        import socket
        host = str(self._arg(args, 'host', '')).strip()
        port = str(self._arg(args, 'port', '')).strip()
        if not host or not port:
            state = self._read_state()
            mode = state.get('mode', 'client')
            base_addr = state.get('base_addr', '').strip()
            if not base_addr:
                return self._err('尚未保存连接配置，请先在连接配置页保存')
            host, port = self._split_addr(base_addr, '', '2333')
        else:
            mode = str(self._arg(args, 'mode', 'client')).strip()
        if not host or not port:
            return self._err('连接地址不完整')
        try:
            port_num = int(port)
        except Exception:
            return self._err('端口格式错误')
        test_host = '127.0.0.1' if host in ('0.0.0.0', '::') else host
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((test_host, port_num))
            sock.close()
        except socket.timeout:
            return self._err('连接 %s:%s 超时（5 秒），请检查网络和防火墙' % (test_host, port_num))
        except Exception as exc:
            return self._err('连接测试异常：%s' % exc)
        if result == 0:
            if mode == 'server':
                return self._ok('Rathole 服务端端口 %s 正在监听，连接正常' % port)
            else:
                return self._ok('成功连接到 %s:%s，网络畅通' % (test_host, port))
        else:
            if mode == 'server':
                return self._err('端口 %s 未监听，Rathole 可能未启动或监听配置有误' % port)
            else:
                return self._err('无法连接到 %s:%s，请检查服务器地址和防火墙设置' % (test_host, port))

    def validate_config(self, args):
        if not os.path.isfile(self.BINARY):
            return self._err('请先安装 Rathole 核心')
        try:
            state = self._validate_saved_state()
            return self._ok('配置检查通过：%s 模式，%d 条规则' % (
                '服务端' if state.get('mode') == 'server' else '客户端',
                len(state.get('services', [])),
            ))
        except Exception as exc:
            return self._err('配置检查失败：%s' % exc)

    def service_action(self, args):
        action = str(self._arg(args, 'cmd', '')).strip().lower()
        if action not in ('start', 'stop', 'restart', 'enable', 'disable'):
            return self._err('不支持的服务操作')
        if action in ('start', 'restart'):
            if not os.path.isfile(self.BINARY):
                return self._err('请先安装 Rathole 核心')
            try:
                self._validate_saved_state()
            except Exception as exc:
                return self._err('不能启动：%s' % exc)
        rc, out = self._run(['systemctl', action, self.SERVICE], timeout=20)
        if rc != 0:
            return self._err(out or ('systemctl %s 失败' % action))
        if action in ('start', 'restart'):
            # Give systemd a moment to catch immediate configuration failures.
            rc2, _ = self._run(['systemctl', 'is-active', '--quiet', self.SERVICE], timeout=5)
            if rc2 != 0:
                _, logs = self._run(['journalctl', '-u', self.SERVICE, '-n', '12', '--no-pager', '-o', 'cat'], timeout=8)
                return self._err('Rathole 启动失败：%s' % (logs or '请查看运行日志'))
        return self._ok('操作完成')

    def get_logs(self, args):
        try:
            lines = int(self._arg(args, 'lines', 150))
        except Exception:
            lines = 150
        lines = max(20, min(lines, 500))
        rc, out = self._run([
            'journalctl', '-u', self.SERVICE, '-n', str(lines), '--no-pager', '-o', 'short-iso'
        ], timeout=10)
        if rc != 0:
            return self._err(out or '读取日志失败')
        return self._ok('日志读取成功', {'log': out})

    @staticmethod
    def _version_tuple(value):
        nums = re.findall(r'\d+', str(value or ''))
        return tuple(int(x) for x in (nums + ['0', '0', '0'])[:3])

    def _plugin_release(self):
        return self._github_json(self.PLUGIN_API + '/releases/latest')

    @staticmethod
    def _plugin_asset(release, version):
        expected = 'rathole_manager_v%s.zip' % version
        for asset in release.get('assets', []):
            if asset.get('name') == expected and asset.get('browser_download_url'):
                return asset
        raise RuntimeError('GitHub Release 中未找到插件安装包：%s' % expected)

    def get_plugin_update(self, args):
        try:
            release = self._plugin_release()
            tag = str(release.get('tag_name', '')).strip()
            latest = tag[1:] if tag.startswith('v') else tag
            if not latest:
                raise RuntimeError('GitHub Release 缺少版本号')
            return self._ok('插件版本检查完成', {
                'current': self.PLUGIN_VERSION,
                'latest': latest,
                'available': self._version_tuple(latest) > self._version_tuple(self.PLUGIN_VERSION),
                'tag': tag,
                'changelog': release.get('body', ''),
                'published_at': release.get('published_at', ''),
            })
        except Exception as exc:
            return self._err('检查插件更新失败：%s' % exc)

    def install_plugin_update(self, args):
        try:
            release = self._plugin_release()
            tag = str(release.get('tag_name', '')).strip()
            latest = tag[1:] if tag.startswith('v') else tag
            if not latest:
                raise RuntimeError('GitHub Release 缺少版本号')
            if self._version_tuple(latest) <= self._version_tuple(self.PLUGIN_VERSION):
                return self._ok('当前已是最新版本：%s' % self.PLUGIN_VERSION)

            asset = self._plugin_asset(release, latest)
            download_url = asset.get('browser_download_url', '')
            expected_digest = str(asset.get('digest', '') or '').strip().lower()
            if expected_digest and not expected_digest.startswith('sha256:'):
                raise RuntimeError('Release 安装包摘要格式无效')

            os.makedirs(self.PLUGIN_DIR, exist_ok=True)
            backup = os.path.join(self.STATE_DIR, 'plugin-backup-' + self.PLUGIN_VERSION)
            os.makedirs(backup, exist_ok=True)
            allowed = {
                'index.html', 'rathole_manager_main.py', 'install.sh', 'info.json',
                'README.md', 'CHANGELOG.md', 'icon.png'
            }
            required = {'index.html', 'rathole_manager_main.py', 'install.sh', 'info.json'}

            with tempfile.TemporaryDirectory(prefix='rathole-plugin-update-') as temp_dir:
                archive_path = os.path.join(temp_dir, 'plugin.zip')
                req = urllib.request.Request(download_url, headers={
                    'Accept': 'application/octet-stream',
                    'User-Agent': 'BT-Rathole-Manager/%s' % self.PLUGIN_VERSION,
                })
                with urllib.request.urlopen(req, timeout=120) as response, open(archive_path, 'wb') as output:
                    shutil.copyfileobj(response, output)

                if expected_digest:
                    import hashlib
                    digest = hashlib.sha256()
                    with open(archive_path, 'rb') as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
                            digest.update(chunk)
                    actual = 'sha256:' + digest.hexdigest()
                    if actual != expected_digest:
                        raise RuntimeError('Release 安装包 SHA256 校验失败')

                extract_dir = os.path.join(temp_dir, 'extract')
                os.makedirs(extract_dir, exist_ok=True)
                with zipfile.ZipFile(archive_path, 'r') as archive:
                    members = []
                    for item in archive.infolist():
                        if item.is_dir():
                            continue
                        name = os.path.basename(item.filename)
                        if not name or name not in allowed or item.filename != name:
                            raise RuntimeError('Release 安装包包含非法文件：%s' % item.filename)
                        members.append(name)
                        with archive.open(item) as src, open(os.path.join(extract_dir, name), 'wb') as dst:
                            shutil.copyfileobj(src, dst)

                missing = required.difference(members)
                if missing:
                    raise RuntimeError('Release 安装包缺少必要文件：%s' % ', '.join(sorted(missing)))

                py_file = os.path.join(extract_dir, 'rathole_manager_main.py')
                rc, out = self._run([sys.executable, '-m', 'py_compile', py_file], timeout=15)
                if rc != 0:
                    raise RuntimeError('新版 Python 检查失败：%s' % out)

                info_file = os.path.join(extract_dir, 'info.json')
                with open(info_file, 'r', encoding='utf-8') as handle:
                    info = json.load(handle)
                if str(info.get('versions', '')).strip() != latest:
                    raise RuntimeError('新版 info.json 版本号与 Release 不一致')

                install_file = os.path.join(extract_dir, 'install.sh')
                rc, out = self._run(['/bin/bash', '-n', install_file], timeout=15)
                if rc != 0:
                    raise RuntimeError('新版 install.sh 检查失败：%s' % out)

                replaced = []
                try:
                    for name in members:
                        src = os.path.join(extract_dir, name)
                        dst = os.path.join(self.PLUGIN_DIR, name)
                        if os.path.isfile(dst):
                            shutil.copy2(dst, os.path.join(backup, name))
                        tmp_dst = dst + '.update-tmp'
                        shutil.copy2(src, tmp_dst)
                        os.replace(tmp_dst, dst)
                        if name.endswith('.py') or name.endswith('.sh'):
                            os.chmod(dst, 0o755)
                        replaced.append(name)
                except Exception:
                    for name in replaced:
                        old_file = os.path.join(backup, name)
                        if os.path.isfile(old_file):
                            shutil.copy2(old_file, os.path.join(self.PLUGIN_DIR, name))
                    raise

            return self._ok('插件已更新到 %s，请关闭并重新打开当前设置窗口' % latest, {
                'version': latest,
                'backup': backup,
            })
        except Exception as exc:
            return self._err('插件在线更新失败：%s' % exc)
