<div align="center">
  <h1>DNSHE 免费域名自动续期</h1>
  <p>每周自动检查 DNSHE 域名，到期前自动免费续期</p>
  <p>简体中文 | <a href="README.en.md">English</a></p>
  <p>
    <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-3776AB">
    <img alt="Platform" src="https://img.shields.io/badge/platform-GitHub%20Actions-2088FF">
    <img alt="License" src="https://img.shields.io/badge/license-MIT-111827">
    <img alt="Schedule" src="https://img.shields.io/badge/schedule-Weekly-22c55e">
  </p>
</div>

> 只需 3 分钟部署，之后每周自动检查并续期你的 DNSHE 免费域名。

## 3 分钟部署

### 第 0 步：获取 DNSHE API 凭证

打开：

- https://my.dnshe.com

准备好这两个值：

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`

### 第 1 步：用 GitHub Importer 转成私有仓库

1. 登录 GitHub，打开 <https://github.com/new/import>
2. 按以下信息填写：

| 字段 | 填什么 |
| --- | --- |
| `Your old repository's clone URL` | `https://github.com/OUBIGFA/dnshe-auto-renew` |
| `Owner` | 你的 GitHub 账号 |
| `Repository name` | 你的仓库名，例如 `my-dnshe-auto-renew` |
| `Privacy` | 选 `Private` |

3. 点击 `Begin import`，等待导入完成（通常几十秒到几分钟）
4. 导入完成后，GitHub 会生成一个属于你自己的私有仓库，后续的 Secrets、Variables 和 workflow 都在这个仓库里设置

### 第 2 步：添加 GitHub Secrets 和 Variable

进入：

- `Settings -> Secrets and variables -> Actions`

添加 Secrets：

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`

添加 Variable：

- `DNSHE_DOMAINS`

### 第 3 步：配置域名

`DNSHE_DOMAINS` 一行一个域名：

```text
abc88.cc.cd
12366.cc.cd
```

### 第 4 步：手动运行一次

打开 GitHub 的 `Actions`，手动运行 `DNSHE Auto Renew`。

第一次运行会检查域名并生成 `state/domains-state.json`。之后工作流每周自动运行一次。

## 域名管理

### 填写格式

一行一个域名，新增就加一行，删除就删一行：

```text
abc88.cc.cd
12366.cc.cd
444.cc.cd
```

### 新增域名

只需把新域名追加到 `DNSHE_DOMAINS`。下一次 workflow 运行时，会自动发现新域名、从 API 读取 `created_at`，自动计算初始到期时间（`created_at + 365` 天），将结果写入 `state/domains-state.json`。不需要手动填注册时间或到期时间。

### 为什么不用手填到期时间

- 第一次发现域名时，用 `created_at + 365` 天推算初始到期时间
- 续期成功后，用 API 返回的 `new_expires_at` 更新状态
- 后续自动滚动计算，不需要每年改日期

## 续期规则

默认规则：

- 免费续期窗口：到期前 `175` 天
- 每周检查一次
- 只有进入窗口后才会请求续期

## 重新生成 API 凭证

如果你在 DNSHE 后台重新生成了 API 凭据，同步更新 GitHub Secrets 即可：

- `DNSHE_API_KEY`
- `DNSHE_API_SECRET`

## 修改执行时间

编辑 `.github/workflows/dnshe-auto-renew.yml` 中的 `cron` 字段。当前为每周一次，时间使用 UTC。

## 文件说明

- `scripts/dnshe_auto_renew.py`：续期脚本
- `.github/workflows/dnshe-auto-renew.yml`：每周 GitHub Actions 工作流
- `state/domains-state.json`：运行后自动生成的状态文件

## 官方文档

- [DNSHE 后台](https://my.dnshe.com)
- [DNSHE API 手册](https://my.dnshe.com/knowledgebase/1/Free-Domain-Name-Service-API-User-Manual.html)

## 许可证

MIT License
