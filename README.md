# AI-QUANT

AI-QUANT 是一个面向红枣期货研究的前后端分离系统：Vue 3 提供可审计的研究界面，Spring Cloud Alibaba 业务服务负责网关、行情与策略编排，Python 算法服务负责实证计算，PostgreSQL 保存策略快照。

系统不生成演示行情，也不为缺失数据填充常量。上游不可用时，对应维度显示 `UNAVAILABLE` 并退出综合评分。

## 分析结构

系统综合决策由 **11 个实证维度**（合计 91%）与 **3 个中华传统文化参考维度**（各 3%，合计 9%）共同加权评分：

| 维度 | 主要真实输入 | 权重 | 属性 |
| --- | --- | ---: | :---: |
| 量价动能 | 东方财富实时行情、真实日 K | 13% | 实证 |
| 产区气象与物候 | Open-Meteo 若羌、阿克苏、喀什预报 | 11% | 实证 |
| 技术指标 | 真实日 K（MA、RSI、BOLL、KDJ、ATR） | 11% | 实证 |
| 供需压力 | 价格、成交量、持仓量同向演化 | 9% | 实证 |
| 执行与风险 | ATR、支撑阻力与区间位置 | 9% | 实证 |
| 持仓拥挤度 | 真实历史持仓量 Z-Score | 8% | 实证 |
| 新闻舆情 | 东方财富红枣资讯词频与情感倾向 | 7% | 实证 |
| 交割与交易规则 | 当前涨跌停和保证金规则使用率 | 7% | 实证 |
| 主力跨期价差 | 按合约到期日排序的近月/跨期溢价 | 6% | 实证 |
| 期限结构 | 多合约真实曲线斜率与结构形态 | 5% | 实证 |
| 流动性与波动状态 | 实时成交量比与 20 日收益波动率 | 5% | 实证 |
| 六爻时历参考 | Asia/Shanghai 真实时间起卦与动爻修正 | 3% | 文化辅助 |
| 易经时序参考 | 公历日序六十四卦循环映射与节气转换 | 3% | 文化辅助 |
| 奇门时九星参考 | 真实时刻时九星与奇门星名吉凶定式 | 3% | 文化辅助 |

中华传统文化参考利用 `lunar-python` 基于中国标准时间计算四柱、节气、空亡和时九星，并依据《易传》经典卦名吉凶矩阵与奇门九星定式输出透明辅助评分（权重各 3%）。文化维度为量价信号提供时序背景参考，但绝不单独替代量价与风险控制维度。当任意实证数据源暂时不可用时，系统显式标记 `UNAVAILABLE` 并按剩余有效维度权重归一化重新计算。

## 架构

```text
Browser :8088
  -> Nginx / Vue 3
  -> Spring Cloud Gateway :8080 (host :18080)
      -> Market Service
      -> Strategy Service -> PostgreSQL / Redis
                          -> Python Algorithm Service
                              -> Eastmoney / Sina / Open-Meteo
```

基础设施还包括 Nacos、Redis、PostgreSQL 和 RocketMQ。服务均提供健康检查，策略服务使用缓存、并发去重、超时与熔断保护；算法服务并发抓取相互独立的证据源，并对短期可复用数据使用线程安全 TTL 缓存。

## Docker 启动

本项目只要求本机安装 Docker Desktop：

```powershell
cd infrastructure
docker compose --env-file .env.example up -d --build
```

启动后访问：

- 前端：http://127.0.0.1:8088
- 网关：http://127.0.0.1:18080
- 网关健康检查：http://127.0.0.1:18080/actuator/health

查看状态：

```powershell
docker compose --env-file .env.example ps
docker compose --env-file .env.example logs --tail=100 algorithm-service strategy-service gateway-service frontend
```

## 验证

```powershell
python -m pytest -q
cd frontend
npm run test
npm run build
```

Java 服务测试可直接在对应 Maven 3.9 / JDK 17 容器中运行，生产镜像构建阶段也会完成编译。

## 关键目录

```text
algorithm_service/        FastAPI 接口与证据并发编排
backend/                  Spring Cloud Gateway、行情与策略服务
data/                     行情、K 线和外部证据采集
engines/                  11 个实证维度、3 个文化参考及融合引擎
frontend/                 Vue 3 用户界面
docs/adr/                 架构决策记录
docs/plans/               实施计划
tests/                    Python 契约、采集和融合测试
```

## 数据与免责声明

每个维度输出数据状态、来源名称、来源链接、观测时间、样本数和实际权重。第三方公开接口可能出现延迟、维护或访问限制；系统会显式降级，不将缓存或文化内容冒充为实时交易证据。

本系统仅供研究和软件验证，不构成投资建议、收益承诺或自动下单授权。期货交易风险较高，请独立核验交易所规则和行情。
