# 账号、真实邮箱与多租户

## 首次启用

1. 在 `infrastructure/.env` 中设置 `IDENTITY_INTERNAL_SECRET`，至少 32 个随机字符。身份服务、网关和两个私有业务服务必须使用相同值；未配置时拒绝启动，没有内置共享密钥。
2. 配置 `PUBLIC_APP_URL`，例如 `https://quant.example.com`。邮件链接使用此地址，不信任请求中的 Host。HTTPS 部署设置 `AUTH_COOKIE_SECURE=true`；本机 HTTP 调试才设为 `false`。
3. 更新构建 `identity-service`、`gateway-service`、`paper-trading-service`、`chanlun-service` 和 `frontend`。既有数据库由 Flyway V8 增加租户列、RLS 和租户外键；升级前按现有运维流程备份。数据库迁移账号须有创建/授权 `aiquant_tenant` 角色的权限。
4. 首次启动默认创建 `admin / admin123456`。初始密码规则统一为「账号 + 123456」，包括注册账号和管理员重置；首次登录必须改密后才能进入业务。启动只创建缺失管理员，不会在重启时重置密码。
5. 登录后从顶栏账号进入 `/account`，可管理工作空间、成员、会话、接口密钥和审计。默认管理员完成改密后可在「安全与会话」绑定真实邮箱。

随机密钥可用 PowerShell 生成后仅保存到本地环境文件：

```powershell
$identityBytes = New-Object byte[] 32
[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($identityBytes)
[Convert]::ToBase64String($identityBytes)
```

本次实现不自动修改当前运行环境的 `.env`，不自动执行生产数据库迁移。

## SMTP 配置

| 环境变量 | 说明 |
| --- | --- |
| `SMTP_HOST` / `SMTP_PORT` | 服务商 SMTP 地址与端口，默认 587 |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP 账号与服务商授权码，不能提交进 Git |
| `SMTP_FROM` | 经过服务商允许的发件地址 |
| `SMTP_AUTH` | 默认 true |
| `SMTP_STARTTLS` | 默认 true；启用时要求 STARTTLS 升级成功 |
| `SMTP_SSL` | 默认 false；服务商要求 465 隐式 TLS 时设为 true，并关闭 STARTTLS |
| `PUBLIC_APP_URL` | 邮件中验证／重置链接的应用地址 |

未配置或 SMTP 发送失败时，注册／重发／找回／绑定邮箱返回明确错误，不返回验证令牌、不显示演示验证码，不将失败发信标为成功。注册事务随发送失败回滚；发送成功仅表示 SMTP 服务接受邮件，最终送达、垃圾箱分类、SPF/DKIM/DMARC 仍需使用所选服务商验证。暂未配置 SMTP 时，默认管理员仍可登录、改密和管理系统。

新用户先注册账号与邮箱，使用邮件中的链接进行显式确认，然后以初始密码登录并改密。验证与重置链接 30 分钟有效、单次使用；令牌放在 URL fragment，不进入 Web 服务访问日志。数据库仅保存令牌摘要。绑定新邮箱需要当前密码及新邮箱确认，成功后撤销旧会话与接口密钥。

## 租户和权限

- 用户身份全局唯一，账号/邮箱规范化为小写。用户可属于多个租户；验证注册邮箱后自动创建自己的工作空间。
- 角色：`OWNER` 所有者、`ADMIN` 管理员、`MEMBER` 可读写成员、`VIEWER` 只读成员。工作空间必须保留至少一名所有者。管理员可添加已完成邮箱验证的账号；所有者负责管理员与所有者角色。
- 平台管理员管理账号启停和初始密码重置、查看平台工作空间信息；平台管理员身份不自动获得其他租户的私有记录访问权。成员关系仍需显式建立。
- 历史模拟账户、工作流、个人训练、笔记与缠论记录归入固定默认租户 `00000000-0000-0000-0000-000000000001`。新租户看不到这些历史记录。
- 市场行情、公开研报及内置书籍目录是公共研究资料。自建书籍和读书感悟均为租户私有；内置书籍目录跨租户只读，感悟按租户隔离。
- 现有浏览器研究日志使用用户 ID 和租户 ID 分区。旧的未分区本地日志保留原键，不自动导入其他账号；可在升级前导出。

所有外部业务 API 由 Gateway 在线校验登录或密钥、账号状态、成员关系和权限，再签发 30 秒有效的内部身份。客户端提供的内部身份／服务密钥头会被剥离。私有业务服务校验签名，整个请求使用事务局部角色和租户变量执行 SQL；`aiquant_tenant` 是 NOLOGIN/NOBYPASSRLS 角色。每张私有表开启 FORCE RLS，跨租户外键阻止将私有子记录挂到其他租户父记录。后台监控写入继承所属租户。

`SET LOCAL` 在提交/回滚后清除，兼容 PgBouncer transaction pooling。后台维护任务仍为受信任的跨租户任务；当前兼容既有迁移/工作线程数据库凭据。生产 SaaS 环境应进一步分离迁移账号、工作线程账号和 HTTP 运行账号：HTTP 账号仅拥有切换 `aiquant_tenant` 的权限，不能创建角色或绕过 RLS。算法/业务服务不得直接暴露到公网；当前 Compose 仅发布前端和网关业务入口。

## 会话与平台接入

浏览器使用 7 天有效、可撤销的 HttpOnly/SameSite=Lax 会话 cookie。修改、绑定邮箱、找回或管理员重置密码会撤销全部会话与接口密钥。Cookie 认证的写请求要求 `X-CSRF-Token`，前端自动附加；密码用 BCrypt cost 12 保存。注册发信和失败登录具备数据库限流，审计不记录密码、令牌或 SMTP 凭据。

接口密钥在 `/account` 的「平台接入」生成，仅显示一次。密钥固定绑定用户及一个租户，最长 365 天，可立即撤销；`READ` 允许 GET/HEAD，`READ_WRITE` 允许角色授权的写操作。每次请求重新检查成员关系和账号状态。接口密钥不能操作账号管理接口。

```http
GET /api/v1/options/catalog
Authorization: Bearer aqk_...
```

浏览器跨工作空间可携带 `X-Tenant-Id`；服务端总是验证成员关系。接口密钥不能切换到其他租户。当前已提供租户化 REST 接入及 `external_identity(provider,subject,user_id)` 扩展表；尚未实现 OIDC/OAuth 登录提供方、SAML、SCIM、订阅计费或第三方平台专属适配器。

## API 概览

公共：`/api/v1/auth/config`、`register`、`login`、`verify`、`resend`、`forgot`、`reset`、`verify-email`。

登录后：`me`、`logout`、`change-password`、`email`、`sessions`、`sessions/{id}/revoke`、`tenants`、`tenants/switch`、`members`、`members/{id}/remove`、`keys`、`keys/{id}/revoke`、`audit`。

独立后台：主系统顶部「后台管理 ↗」进入 `/admin`，管理接口为 `/api/v1/auth/manage/*`。租户、账号、角色权限、菜单、用户授权、访问撤销与日志详见 [admin-console.md](admin-console.md)。保留兼容接口 `admin/users`、`admin/tenants`、`admin/users/{id}/enabled`、`admin/users/{id}/reset-initial`。内部 introspection 为 `/internal/v1/identity/introspect`，不通过公网网关路由。

## 验证

使用独立测试数据库（数据库名必须包含 `identity_test`），测试自行重建 identity、paper_trading 和 chanlun schema，禁止指向业务数据库：

```powershell
$env:IDENTITY_TEST_DATABASE_URL='jdbc:postgresql://127.0.0.1:55439/identity_test'
# 独立测试数据库用户 identity_test；测试密码 isolated-test-only
mvn -s maven-settings.xml -pl identity-service,tenant-security,gateway-service,paper-trading-service,chanlun-service -am test
```

邮箱协议测试启用本机临时 SMTP 接收器，确实发送 MIME 邮件；它不代表外部服务商送达验证。安全测试覆盖验证/重置令牌重放、过期、缺少 SMTP、失败登录限流、CSRF、会话撤销、初始强制改密、角色、接口密钥、旧数据归属、RLS 和跨租户外键。

2026-11-06 账号、期权已更新到 `ai-quant`，并完成实际登录、CSRF、首次改密限制及已有数据租户隔离检查，见 [部署记录](deployment-2026-11-06.md)。后台扩展验证新增 11 项数据库权限测试，连同账号和网关共 32 项测试全部通过；前端全量 298 项测试及最新页面调整后的 12 项针对检查通过，类型检查与生产构建通过。外部 SMTP 服务商尚未配置，真实外部投递尚待配置后验证。

参考：[Spring Security 密码存储](https://docs.spring.io/spring-security/reference/6.5/features/authentication/password-storage.html)、[PostgreSQL 行级安全](https://www.postgresql.org/docs/17/ddl-rowsecurity.html)。
