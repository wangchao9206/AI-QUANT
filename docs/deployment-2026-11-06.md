# 2026-11-06 期权与账号部署记录

已按用户授权部署到原有 Docker Compose 项目 `ai-quant`，入口保持 http://localhost:8088 。

更新服务：identity-service（新增）、algorithm-service、paper-trading-service、chanlun-service、gateway-service、frontend。其他项目容器未操作。上述六项服务均通过健康检查。

## 数据与配置

- 部署前 PostgreSQL 完整自定义格式备份保存到 `.test-tmp/deployment-20261106-accounts-options/database.dump`，已通过 pg_restore --list 校验。
- 原镜像保留 `before-accounts-options-20261106` 标签。数据库已迁移至 identity V1、paper_trading V8、chanlun V8；镜像回退不等同数据库回退，应先核对兼容性。
- 本地 infrastructure/.env 新增随机身份内部密钥、PUBLIC_APP_URL=http://localhost:8088、AUTH_COOKIE_SECURE=false（当前本机 HTTP 入口）。未输出或提交真实密钥；HTTPS 上线时应启用 Secure cookie。
- 默认账号 admin，初始密码 admin123456，登录检查没有修改该密码。仍要求首次登录改密。
- SMTP 未配置，邮箱操作将明确提示需要配置发信服务。

## 构建与运行

Docker 内 Maven 构建等待较久，最终使用此前已验证源码在本机 Maven 3.9.9 打包，将可执行 JAR、生产前端产物和期权 Python 模块装入原运行镜像。部署构建上下文与日志保存在 `.test-tmp/deployment-20261106-accounts-options/`。仓库标准 Dockerfile 与 Compose 路径保留。

旧应用容器重建期间发生 Docker 退出事件延迟和僵尸进程，已移除并重建对应应用容器，数据库及数据卷未删除。Compose 增加 init 配置以改善后续进程回收；当前身份和算法容器在此配置变更之前创建，后续重建时应用该项设置。

## 上线验证

- 登录、期权和账号前端路径均返回正常页面。
- 未登录业务访问 401；管理员初始登录成功，默认租户与平台管理员标志正确；未改密业务访问 403。
- 缺少 CSRF 的退出请求 403，携带正确 CSRF 后退出成功。
- 模拟账户总数 17，默认租户可见 17，其他租户可见 0；验证事务已回滚，没有修改业务记录。
- 天勤实际目录返回 FRESH，450 条期权链。抽查一条链为 CACHED，36 个合约、34 个有报价、27 个可计算 IV；缺失值未补造。
- 真实外部 SMTP 送达尚未验证，需后续配置服务商。

同日后续已部署独立后台，见 [后台部署记录](deployment-admin-2026-11-06.md)。管理员已在后续部署前自行完成首次改密，请使用当前密码；上述初始密码检查为首次部署时的历史结果。
