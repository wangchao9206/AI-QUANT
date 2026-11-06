# 2026-11-06 期权盘口与后台持续监控部署

已部署到原有 `ai-quant` 项目，入口 http://localhost:8088/live 。页面增加「对应期权与监控」「期货后台监控」标签，支持真实期权盘口与九周期图表、23 类可配置监控条件、后台持续求值及租户内持久触发记录。需要在界面保存并启用任务；正式数据库没有创建验收任务。

更新 identity-service、algorithm-service、market-service、gateway-service、frontend，五项健康。algorithm-service 与 Java 服务共享内部鉴权密钥，market-service 显式配置 identity-service 地址；Compose 配置校验通过。market V2 迁移成功，三个新私有表均启用 FORCE RLS；现有 17 个模拟交易会话保留，管理员仍启用且无需重新修改密码，没有使用或重置其现有密码。

## 备份与回退

- PostgreSQL 完整自定义格式备份：`.test-tmp/deployment-monitor-20261106/database.dump`，10,822,053 字节，`pg_restore --list` 验证 529 个归档条目。
- 五个旧镜像保留 `before-options-monitor-20261106` 标签。运行构建上下文在 `.test-tmp/deployment-monitor-20261106/runtime/`，标准仓库 Dockerfile 保留。
- 新表迁移为增量新增，回退镜像不会删除数据库记录；恢复数据库前需单独核对后续业务写入，不要用镜像回退替代数据库恢复。

## 验证

- Python 相关规则、行情和 API 回归 284 项通过；最后收紧一分钟报价窗口边界后，规则测试 17 项全部通过，新增不规则采样不计入 60 秒外涨幅的回归。
- Java 首轮相关模块 51 项通过，随后增加到期自动停用与事件写入失败整体回滚测试，market-service 最终 18 项、tenant-security 1 项通过；identity 25 项、Gateway 9 项此前通过。包含真实 PostgreSQL RLS、跨租户／资产隔离、乐观锁、暂停后的在途结果丢弃、租约、事件去重、持久状态和撤权。
- 前端 63 个文件、337 项测试通过，类型检查及最终生产构建通过。
- 真实 HTTP 联调使用独立 PostgreSQL、实际 identity-service/market-service JAR 和明确标记的测试行情：浏览器不再发请求时仍新增持久事件；暂停后无新增、版本冲突 409、已读、期权资产隔离、跨租户 404、撤权后 FORBIDDEN 均通过。测试数据库容器、两个 Java 进程和行情验收服务已停止并移除，不含正式任务。
- 桌面与 390px 手机浏览器验收显示 23 项规则、五项均线配置、期权九周期、买卖档位与触发依据，无整页横向溢出、无浏览器异常。界面测试数据只在隔离服务中使用。
- 正式 `/live`、`/admin`、`/options`、`/login` 与新构建首页一致；LiveView、TongdaxinChart、入口 JS/CSS 字节一致。未登录访问期货／期权任务、记录与期权盘口均为 401。
- 实际天勤目录 450 条链。RBM 精确解析为 RB2701，匹配 1 条真实期货期权链；实际 `SHFE.rb2701C3050` 买卖各 5 档、71 个 Tick 成交增量、600 根 1 分钟柱，OHLC 校验通过，源时点为 `2026-11-06T14:59:59.999500+08:00`。检查发生在收盘后，状态 CACHED；真实期货／期权首次后台求值均为 STALE、没有历史触发。

后台监控使用独立调度线程和工作池，不依赖页面或 RocketMQ 广播。检查时行情广播日志存在 RocketMQ 发送超时；此次没有改动其配置，监控仍直接读取主源接口并保存到 PostgreSQL。

规则口径、窗口预热、主连固定交割月、大额成交估算方向、权限、订阅与任务容量见 [live-monitoring.md](live-monitoring.md)。
