# Fragment Premium Gift Bot

Fragment Premium Gift Bot 是一个独立的 Python Telegram bot 项目，用于通过 Fragment 创建 Telegram Premium 礼物订单，读取 `rawRequest` 的金额和付款备注，再用 TON 钱包完成付款。

项目默认开启 dry-run，不会直接转账；同时加了管理员白名单、二次确认、最大付款金额限制和 `.env` 本地配置，尽量降低误操作风险。

## 安装

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

复制完成后编辑 `.env`。所有密钥、Cookie、助记词都只放在 `.env`，不要提交到仓库，也不要发给别人。

## .env 配置总览

```dotenv
TELEGRAM_BOT_TOKEN=1234567890:AAExampleBotToken
TELEGRAM_ADMIN_IDS=123456789,987654321

FRAGMENT_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
FRAGMENT_COOKIE="stel_ssid=...; stel_token=...; ..."

WALLET_MNEMONIC="word1 word2 word3 ... word24"

PAYMENT_DRY_RUN=true
ALLOWED_DURATIONS=3,6,12
MAX_TON_AMOUNT=100
CONFIRM_TTL_SECONDS=300

FRAGMENT_WALLET_ADDRESS=EQBAjaOyi2wGWlk-EDkSabqqnF-MrrwMadnwqrurKpkla9nE
STRICT_FRAGMENT_WALLET=false
SHOW_SENDER=true

TONCENTER_API_KEY=
TON_TESTNET=false

REQUEST_TIMEOUT=20
LOG_LEVEL=INFO
```

## 必填配置

### `TELEGRAM_BOT_TOKEN`

用途：Telegram bot 的访问令牌，程序用它连接 Telegram Bot API。

怎么获取：

1. 打开 Telegram，搜索官方 bot `@BotFather`。
2. 发送 `/newbot`。
3. 按提示填写 bot 显示名称。
4. 再填写 bot 用户名，用户名必须以 `bot` 结尾，例如 `my_premium_helper_bot`。
5. BotFather 会返回一串 token，格式通常像 `1234567890:AA...`。

怎么填写：

```dotenv
TELEGRAM_BOT_TOKEN=1234567890:AAExampleBotToken
```

注意：不要加 `bot` 前缀，不要加 URL，只填 BotFather 给你的 token。泄露后可以在 `@BotFather` 里用 `/mybots` 重新生成。

### `TELEGRAM_ADMIN_IDS`

用途：允许操作这个 bot 的 Telegram 数字用户 ID。只有这里列出的用户才能创建订单和确认付款。

推荐获取方式：

1. 先创建 bot 并拿到 `TELEGRAM_BOT_TOKEN`。
2. 在 Telegram 里打开你自己的 bot，发送任意消息，比如 `/start`。
3. 浏览器打开 `https://api.telegram.org/bot你的TOKEN/getUpdates`。
4. 在返回 JSON 中找 `message.from.id`，这个数字就是你的用户 ID。

备选方式：使用 Telegram 里的查 ID 工具 bot，例如 `@userinfobot`。这类 bot 不是本项目依赖，只用于查看自己的数字 ID。

怎么填写：

```dotenv
TELEGRAM_ADMIN_IDS=123456789
```

多个管理员用英文逗号分隔：

```dotenv
TELEGRAM_ADMIN_IDS=123456789,987654321
```

注意：这里填的是数字 ID，不是 `@username`。建议先只填你自己的 ID，确认流程稳定后再增加其他管理员。

### `FRAGMENT_HASH`

用途：Fragment 网页接口路径里的 hash。程序会请求 `https://fragment.com/api/v1/<FRAGMENT_HASH>`。

怎么获取：

1. 用 Chrome 或 Edge 打开 [https://fragment.com](https://fragment.com)，登录你的 Telegram 账号。
2. 按 `F12` 打开开发者工具，切到 `Network` 面板。
3. 勾选 `Preserve log`，过滤器里输入 `api/v1`。
4. 在 Fragment 页面里进行一次 Premium 礼物相关操作，例如搜索收礼用户名或进入购买流程。
5. Network 里会出现类似 `https://fragment.com/api/v1/xxxxxxxxxxxxxxxx` 的请求。
6. 复制 `/api/v1/` 后面的那段字符串，填到 `FRAGMENT_HASH`。

怎么填写：

```dotenv
FRAGMENT_HASH=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

注意：只填最后那段 hash，不要填完整 URL。如果 Fragment 页面重新登录、Cookie 失效或接口变更，可能需要重新获取。

### `FRAGMENT_COOKIE`

用途：Fragment 登录态 Cookie。程序需要带着它调用 Fragment 接口创建订单。

怎么获取：

1. 继续使用获取 `FRAGMENT_HASH` 时同一个 Network 请求。
2. 点击该请求，打开 `Headers`。
3. 在 `Request Headers` 里找到 `Cookie`。
4. 复制 `Cookie:` 后面的完整内容。

怎么填写：

```dotenv
FRAGMENT_COOKIE="stel_ssid=...; stel_token=...; other_key=..."
```

注意：建议用英文双引号包起来，整段 Cookie 必须在同一行。Cookie 等同于你的 Fragment 登录凭证，泄露后别人可能能用你的会话下单，请只保存在本机 `.env`。

## 付款相关配置

### `WALLET_MNEMONIC`

用途：TON 钱包助记词。只有 `PAYMENT_DRY_RUN=false` 真实付款时才必须填写。

怎么获取：

1. 打开你的 TON 钱包，例如 Tonkeeper。
2. 进入钱包备份或安全设置。
3. 查看 Recovery Phrase / Seed Phrase / 助记词。
4. 按原顺序复制 24 个英文单词，中间用空格分隔。

怎么填写：

```dotenv
WALLET_MNEMONIC="word1 word2 word3 word4 ... word24"
```

注意：强烈建议使用专门的小额热钱包，不要使用主钱包。助记词拥有钱包全部控制权，任何人拿到都可以转走资产。

### `PAYMENT_DRY_RUN`

用途：控制是否真实发送链上交易。

怎么填写：

```dotenv
PAYMENT_DRY_RUN=true
```

取值说明：

- `true`：模拟模式，只创建 Fragment 订单、解析金额和备注，不会发起 TON 转账。
- `false`：真实模式，点击 bot 的确认按钮后会发送 TON 转账。

建议：第一次部署必须保持 `true`，确认 `/open @username 3` 能正确显示订单后，再改成 `false`。

### `ALLOWED_DURATIONS`

用途：限制 bot 允许开通的 Premium 月份。

怎么填写：

```dotenv
ALLOWED_DURATIONS=3,6,12
```

注意：用户执行 `/open @username 3` 时，第二个参数必须在这个列表里。这个值要和 Fragment 当前支持的 Premium 礼物月份一致。

### `MAX_TON_AMOUNT`

用途：单笔付款金额保护线，超过这个金额 bot 会拒绝确认付款。

怎么填写：

```dotenv
MAX_TON_AMOUNT=100
```

建议：测试阶段可以设小一点，例如：

```dotenv
MAX_TON_AMOUNT=20
```

### `CONFIRM_TTL_SECONDS`

用途：bot 确认按钮的有效时间，单位是秒。过期后需要重新创建订单。

怎么填写：

```dotenv
CONFIRM_TTL_SECONDS=300
```

建议：保持 300 秒即可。Fragment 订单本身也有过期时间，程序会取两者中更早的时间。

### `FRAGMENT_WALLET_ADDRESS`

用途：默认 Fragment 收款地址。当前代码也会优先使用 Fragment `rawRequest` 返回的地址；如果没有返回地址，就使用这里的地址。

默认值：

```dotenv
FRAGMENT_WALLET_ADDRESS=EQBAjaOyi2wGWlk-EDkSabqqnF-MrrwMadnwqrurKpkla9nE
```

怎么获取或确认：一般不需要改。它是当前默认的 Fragment Premium 付款地址兜底值。真实付款前你可以在 bot 订单确认信息里核对收款地址、金额和付款备注。

### `STRICT_FRAGMENT_WALLET`

用途：是否强制校验 Fragment 返回的收款地址必须等于 `FRAGMENT_WALLET_ADDRESS`。

怎么填写：

```dotenv
STRICT_FRAGMENT_WALLET=false
```

取值说明：

- `false`：兼容模式，优先使用 Fragment 返回地址，不强制等于默认地址。
- `true`：严格模式，如果 Fragment 返回地址与默认地址不同，拒绝付款。

建议：不确定 Fragment 是否会变更地址时保持 `false`。如果你只信任固定地址，可以设为 `true`。

### `SHOW_SENDER`

用途：创建 Premium 礼物订单时是否显示赠送者。

怎么填写：

```dotenv
SHOW_SENDER=true
```

取值说明：

- `true`：显示赠送者。
- `false`：不显示赠送者。

## TON Provider 配置

### `TONCENTER_API_KEY`

用途：TON Center API key。真实付款会通过 TON Center HTTP API 发送交易。没有 key 通常也能用，但速率更低。

怎么获取：

1. 在 Telegram 打开 `@tonapibot`。
2. 点击 `Start`。
3. 进入 `Manage API Keys` 或 `TON Center`。
4. 点击 `Create API Key`。
5. 创建后复制 API key。

怎么填写：

```dotenv
TONCENTER_API_KEY=你的ToncenterApiKey
```

不想配置可以留空：

```dotenv
TONCENTER_API_KEY=
```

### `TON_TESTNET`

用途：是否使用 TON 测试网。

怎么填写：

```dotenv
TON_TESTNET=false
```

取值说明：

- `false`：主网，真实 Telegram Premium 付款应使用主网。
- `true`：测试网，只适合开发 TON 转账逻辑，不适合真实 Fragment Premium 订单。

建议：本项目用于 Fragment Premium 时保持 `false`。

## 运行和日志配置

### `REQUEST_TIMEOUT`

用途：请求 Telegram、Fragment、TON Center 的超时时间，单位秒。

怎么填写：

```dotenv
REQUEST_TIMEOUT=20
```

网络慢可以调大，例如：

```dotenv
REQUEST_TIMEOUT=40
```

### `LOG_LEVEL`

用途：控制日志详细程度。

怎么填写：

```dotenv
LOG_LEVEL=INFO
```

常用取值：

- `INFO`：默认，适合生产运行。
- `DEBUG`：排查问题时使用，可能输出更多请求流程信息。
- `WARNING`：只看警告和错误。

## 推荐首次配置流程

1. 复制 `.env.example` 为 `.env`。
2. 先填写 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_ADMIN_IDS`。
3. 填写 `FRAGMENT_HASH` 和 `FRAGMENT_COOKIE`。
4. 保持 `PAYMENT_DRY_RUN=true`。
5. 运行 `python -m premium_bot`。
6. 在 Telegram 里发送 `/config`，确认配置被读取。
7. 发送 `/open @目标用户名 3`，确认能创建订单并显示金额、收款地址、付款备注。
8. 确认 dry-run 流程没问题后，再填写 `WALLET_MNEMONIC`。
9. 把 `MAX_TON_AMOUNT` 设为你能接受的单笔上限。
10. 最后再把 `PAYMENT_DRY_RUN=false` 切到真实付款。

## 运行

```powershell
python -m premium_bot
```

## Debian 服务器运行

推荐使用 Debian 12。Debian 12 默认 Python 3.11，可以直接满足项目的 Python 3.10+ 要求。Debian 11 默认 Python 3.9，不建议直接运行，除非你额外安装 Python 3.10 或更高版本。

### 安装系统依赖

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 上传并安装项目

示例把项目放在 `/opt/fragment-premium-gift-bot`：

```bash
cd /opt
sudo mkdir -p fragment-premium-gift-bot
sudo chown "$USER:$USER" fragment-premium-gift-bot
cd fragment-premium-gift-bot
```

把本地项目文件上传到 `/opt/fragment-premium-gift-bot` 后执行：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
cp .env.example .env
nano .env
```

第一次部署建议保持：

```dotenv
PAYMENT_DRY_RUN=true
```

### 前台测试运行

```bash
source .venv/bin/activate
python -m premium_bot
```

如果 bot 能正常启动，在 Telegram 里发送 `/config` 和 `/open @目标用户名 3` 测试 dry-run 流程。

### systemd 后台运行

创建服务文件：

```bash
sudo nano /etc/systemd/system/fragment-premium-gift-bot.service
```

写入以下内容：

```ini
[Unit]
Description=Fragment Premium Gift Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/fragment-premium-gift-bot
ExecStart=/opt/fragment-premium-gift-bot/.venv/bin/python -m premium_bot
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

启动并设置开机自启：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now fragment-premium-gift-bot
sudo systemctl status fragment-premium-gift-bot
```

查看实时日志：

```bash
journalctl -u fragment-premium-gift-bot -f
```

重启服务：

```bash
sudo systemctl restart fragment-premium-gift-bot
```

停止服务：

```bash
sudo systemctl stop fragment-premium-gift-bot
```

### Debian 运行注意事项

- 这个 bot 使用 Telegram polling，不需要开放服务器入站端口。
- 服务器必须能访问 `api.telegram.org`、`fragment.com`、`toncenter.com`。
- `.env` 里有 bot token、Fragment Cookie 和钱包助记词，建议限制权限：`chmod 600 .env`。
- 切换到真实付款前，先在服务器上完整跑通 `PAYMENT_DRY_RUN=true`。
- 如果服务器无法访问 Telegram，需要额外配置代理支持；当前版本默认走服务器直连网络。

## Bot 命令

- `/start` 或 `/help`：查看用法。
- `/open @username 3`：创建 Telegram Premium 礼物订单，支持的月份由 `ALLOWED_DURATIONS` 控制。
- `/wallet`：查看当前助记词导入后的钱包地址。
- `/config`：查看非敏感运行配置。

## 安全注意

TON 转账不可逆。真实模式下每次点击确认都会发送链上交易，请先用小额钱包、dry-run 和管理员白名单验证完整流程。

如果怀疑信息泄露：

- `TELEGRAM_BOT_TOKEN` 泄露：去 `@BotFather` 重新生成 token。
- `FRAGMENT_COOKIE` 泄露：退出 Fragment 登录会话，重新登录后更新 `.env`。
- `WALLET_MNEMONIC` 泄露：立刻把钱包资产转移到新钱包，不要继续使用旧助记词。

官方文档：

- [Telegram Bot Features - BotFather](https://core.telegram.org/bots/features#botfather)
- [Telegram Bot API - getUpdates](https://core.telegram.org/bots/api#getting-updates)
- [TON Center API key guide](https://old-docs.ton.org/v3/guidelines/dapps/apis-sdks/api-keys)
