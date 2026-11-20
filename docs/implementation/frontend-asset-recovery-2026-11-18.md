# Docker 更新后动态模块加载失败修复

报错的 TodayView-DjLrnBNR.js 来自旧前端镜像。更新前已打开的标签页保留旧入口的模块映射，新容器没有旧资源，导航到今日页便返回404。HTML已经设置no-store，但这无法替换标签页内已经运行的旧代码。

## 改动

- frontend-assets 命名卷只保存公开的哈希构建文件。容器启动脚本以101用户逐文件归档当前assets，先写临时文件再原子改名，不覆盖同名旧文件。Nginx从该卷提供assets，HTML仍由当前镜像提供并设置no-store。容器保持只读根文件系统，静态文件原有MIME、immutable、nosniff、CSP等设置保留。
- 首次迁移用 scripts/seed_frontend_assets.py 从明确指定的本机旧镜像恢复完整assets和依赖树；禁用拉取、禁用网络，只挂载静态资源卷。旧文件按原字节恢复，不把新JS伪装成旧哈希。脚本以原始LF字节传给容器，避免Windows管道换行问题。
- 路由只对动态模块或预加载CSS失败触发一次完整导航，保留目标路径、query和hash。sessionStorage标记确保5分钟内最多自动重载一次；离线、普通业务错误、外部目标或浏览器无法保存标记时不重载。
- frontend/archive-assets.sh 固定LF换行。

## 验证

9项恢复/路由测试通过；前端类型检查及生产镜像构建通过。原报错链接在局域网返回200、application/javascript；替换容器后仍为200。真实LAN浏览器登录、今日页跳转、localhost登录及未知Origin拒绝验证通过。

scripts/qa_frontend_asset_recovery.cjs 以真实本机Docker服务验证旧入口依赖、当前今日/模拟与DKX，以及模拟模块404的一次恢复和持续失败时不刷新循环。拦截HTML的场景使用localhost：Chromium对没有真实对端地址的合成文档会触发局域网地址空间限制；真实LAN访问由独立脚本验证，不修改生产浏览器策略。

原始旧入口及验收回执保留在忽略目录 .test-tmp/frontend-asset-recovery/。

最终浏览器验收全部通过：旧JS与原镜像逐字节SHA256一致，旧入口完整依赖图正常；当前今日、模拟交易及DKX正常；持续阻断首个文档的模块请求后触发一次整页重载并恢复原目标/query/hash；持续阻断两个文档时停止重载，没有循环。带锚点的同URL使用reload，避免location.replace只滚动而未重载。Docker运行用户101:101、只读根文件系统、健康检查和nginx配置检查均通过。
