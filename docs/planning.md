# Dr Panda MCP 规划

线上排查用的 MCP 服务。Cursor、Codex、DeepSeek Harness 通过 Streamable HTTP 调用它，查日志、代码、数据库和消息堆积。连接信息在网页上配置，登录鉴权以后再做。

本文只定方案，不包含实现。

## 目标

模型拿到的是一组只读排查工具，不是线上系统的管理入口。人在网页里登记 MySQL、Mongo、Elasticsearch、Redis、GitLab、RabbitMQ、Kafka、CLS（腾讯云日志服务）的地址、凭证和允许访问的范围。工具在调用时按名字读取这些登记，模型不能自己传入主机、账号或密码。凭证即使带有写权限，本服务对这八个组件发出的请求也全部是只读的。

三个客户端都支持 Streamable HTTP，所以服务以 HTTP 方式提供，路径 `/mcp`。同一进程同时提供给人用的配置网页。

## 已定决策

- 第一版不做登录、不做 Bearer Token、不做 OAuth。网页和 `/mcp` 都先匿名访问。
- 连接与访问范围由网页写入配置库。每台 MySQL、每个 topic 都是配置库里的一行，不写进环境变量。
- 配置库默认是本机 SQLite，并支持换到 MySQL 或 PostgreSQL。三种库共用同一套表、迁移和仓储接口。
- 默认监听 `127.0.0.1:8111`。端口由 `DR_PANDA_PORT` 修改，主机由 `DR_PANDA_HOST` 修改。
- 对八个排查组件绝对只读。账号能否写入不影响这条规则，也没有开关可以放开写入。
- 鉴权留成以后的一层外壳：身份检查加在网页和 `/mcp` 前面。工具、配置库、只读限制都不改。

## 总体形态

一个 Python 进程，两套入口：

| 入口 | 谁用 | 做什么 |
|---|---|---|
| `/` | 人，浏览器 | 登记、修改、停用、测试各个线上目标 |
| `/mcp` | Cursor、Codex、DeepSeek Harness | 调用排查工具 |

FastMCP 4.1.4 的 `custom_route` 就是用来挂这类协议之外的 HTTP 端点的。配置页走这条路径，MCP 仍走 `http_app` 的 `/mcp`。不另起前端工程，也不把配置页做成 MCP App：凭证要在普通浏览器里填写，Codex 和 DeepSeek Harness 也不保证能渲染 MCP 内嵌界面。

默认监听 `127.0.0.1:8111`。端口用 `DR_PANDA_PORT` 修改，监听网卡用 `DR_PANDA_HOST` 修改。需要给别的机器用时，再把主机改成内网地址。当前没有登录，网络可达就等于能查线上数据，也能改已保存的凭证。现阶段的访问控制就是：只在本机或受控内网监听，不要暴露到公网。

stdio 只用于本机调试 MCP 工具，不作为三端的正式接法。正式使用时客户端只配置 URL，例如 `http://127.0.0.1:8111/mcp`。端口改过时，客户端 URL 使用同一个端口。DeepSeek Harness 的 `serverName` 用短名 `drpanda`，模型看到的工具名会是 `mcp__drpanda__mysql_query` 这种形式，所以工具名保持短且稳定。

## 配置网页

服务端渲染的表单页面，样式从简。页面只做配置，不承担排查。

页面：

- `/`：已登记目标的列表。按类型分组，显示名称、是否启用、最近一次连通性测试的结果。
- `/targets/new?type=mysql`：新建。类型为 mysql、mongo、elasticsearch、redis、gitlab、rabbitmq、kafka、cls 之一。
- `/targets/{id}/edit`：修改。
- 提交后保存；另有「测试连接」「启用 / 停用」「删除」。

交互约定：

- 名称是工具参数里的 `target`，创建后不可改，只允许小写字母、数字和连字符，全局唯一。例：`order-mysql`、`pay-redis`。
- 密钥字段（密码、Token、SecretKey）保存后不明文回显。编辑时留空表示沿用原值，勾选清除才去掉。
- 停用的目标仍留在库里，工具拒绝使用它，并说明已停用。
- 测试连接走和正式工具同一套只读闸门，只做最小读操作：MySQL `SELECT 1`，Mongo `ping`，Redis `PING`，Elasticsearch 集群健康或根路径，GitLab 当前用户，RabbitMQ overview，Kafka 元数据，CLS 列出已授权 topic 的一次轻量请求。
- 测试结果（时间、成功或失败、错误摘要）记在目标上，密钥不写进错误信息。

## 配置库

配置库只保存本服务自己的数据：排查目标、密钥、审计。它和网页里登记的线上 MySQL 是两套连接。配置库需要插入、更新和删除；线上 MySQL 只供排查工具做只读查询。配置库的地址来自环境变量，不能登记成一个排查目标，排查工具也不能改配置库。

### 怎么选择

环境变量 `DR_PANDA_DATABASE_URL`。未设置时使用本机 SQLite：

```
sqlite:///data/dr-panda.sqlite
```

`data/` 不进 git。换成另外两种库时只改这个 URL：

```
mysql://user:pass@host:3306/dr_panda
postgresql://user:pass@host:5432/dr_panda
```

进程启动时把 `mysql://` 补成异步驱动 `mysql+asyncmy://`，把 `postgresql://` 补成 `postgresql+asyncpg://`，调用方不用写驱动名。URL 指向某种库但对应驱动没安装时，启动直接失败，并说明要安装哪一组依赖。

默认安装包含 SQLite 驱动，开箱可用。MySQL 和 PostgreSQL 的驱动做成可选依赖：`dr-panda-mcp[mysql]`、`dr-panda-mcp[postgres]`。仓储代码不因装了哪一组依赖而分叉。

监听地址用 `DR_PANDA_HOST`（默认 `127.0.0.1`）和 `DR_PANDA_PORT`（默认 `8111`）。改端口只改这个环境变量，网页和 `/mcp` 一起跟着变。各系统的主机和密钥都在配置库里。

### 扩展缝放在哪里

网页、MCP 工具、连接器只依赖 `ConfigStore` 接口，不出现 SQLite、MySQL 或 PostgreSQL 的类型和 SQL。接口保持很小：

- 按名称或 id 读取目标，按类型列出目标
- 新建、更新、启用、停用、删除
- 写下连通性测试结果
- 追加一条审计

配置变更和对应的审计写入同一次事务提交。

三种库共用一个 SQLAlchemy 2 异步实现，不各写一套仓储。方言差异收拢在三处：URL 解析、引擎创建、Alembic 迁移。SQLite 在建引擎时打开 WAL、外键约束和 `busy_timeout`；这段逻辑不进入仓储语句。再增加一种关系型数据库时，补 URL 方案、驱动依赖，并用下面的同一套契约测试验收，而不是复制一份增删改。

表结构遵守能在三种库上执行的子集：

- 主键用自增整数，不用某种库专有的序列语法
- `type` 用定长字符串，合法值在应用层检查，不用数据库 ENUM
- `enabled`、`last_test_ok` 用布尔
- 时间用带时区的时间戳，应用层一律写 UTC、按 UTC 读出
- `options_json`、`secret_json` 用 JSON 类型，整份读写。第一版不在 SQL 里按 JSON 内部字段过滤，避免依赖某种库的 JSON 运算符
- 字符串给出 MySQL 需要的长度：`name` 64，`type` 32，审计动作 32，调用方 64
- 密钥如果以后要加密，在应用层做，这样三种库的密文格式相同

迁移用 Alembic，一条版本链适用全部方言。进程启动时迁移到最新版本。第一版按单进程使用；以后若多个进程共用同一 MySQL 或 PostgreSQL，再给迁移加锁。

契约测试描述 `ConfigStore` 的行为（唯一名称、密钥不回显给网页、停用后读得到但标记为停用、配置与审计同事务）。开发时这条测试跑在 SQLite 上；把 `DR_PANDA_DATABASE_URL` 指到 MySQL 或 PostgreSQL 时跑同一套，作为这两种库可用的验收。

### 表

`targets`

- `id`
- `type`：mysql、mongo、elasticsearch、redis、gitlab、rabbitmq、kafka、cls
- `name`：唯一的 target 名
- `enabled`
- `options_json`：主机、端口、库名、索引、topic、超时、行数上限等非密钥项
- `secret_json`：密码、Token、云 API 密钥
- `created_at`、`updated_at`
- `last_test_at`、`last_test_ok`、`last_test_error`

`name` 唯一索引，另按 `type` 索引。

`audit`

- `id`、`created_at`
- `actor`：有登录之前为 `anonymous`
- `action`、`target_name`、`summary`
- 配置变更和工具调用都记一条
- 参数中的密钥、手机号、证件号打码后再落盘

按 `created_at` 索引。审计只追加。

工具每次调用都按 `name` 读配置库，所以网页上新增或停用立即生效，不用重启，也不用动态增删 MCP 工具。工具名单保持稳定，避免客户端缓存的工具表和会话记录对不上。某个类型还没有任何启用目标时，对应工具返回明确错误，例如「还没有启用的 MySQL 目标」。第一版不在进程内缓存目标：配置库一次按主键读取足够轻，也可以避免多进程共用 MySQL 或 PostgreSQL 时读到过期配置。

排查用的连接池按 target 懒加载，和配置库的连接池分开。该目标的配置一保存，就丢掉旧的排查连接，下次调用重建。

## 绝对只读

MySQL、Mongo、Elasticsearch、Redis、GitLab、RabbitMQ、Kafka、CLS 的每一次调用，包括网页上的测试连接，都是只读的。用户配进来的账号即使可以插入、更新、删除、建表、清队列、发消息或改配置，本服务也不行使这些权限。

这条规则没有例外开关。网页上不出现「允许写入」。工具列表里没有写操作。连接器不提供「执行任意命令」。新增组件时必须同时交出读方法、闸门，以及「写操作被拒绝且没有发出网络请求」的测试，否则不接入。

闸门放在请求离开进程之前，不依赖对方的账号权限：

1. 按该组件的白名单检查。解析失败、含义不确定、或不在白名单中，就拒绝，请求不发出。
2. 组件若支持会话级只读，连接一建立就打开。这只约束本服务自己的会话，不去修改对方的全局只读开关。
3. 每个组件都有拒绝用例，覆盖直接的写操作和伪装成读的写操作。

### MySQL

只允许单条 `SELECT`、`SHOW`、`DESCRIBE`，以及内层语句同样属于这个白名单的 `EXPLAIN`。用 SQL 解析器看语法树。以 `SELECT` 开头的字符串不能作为放行依据。

拒绝多语句、`INSERT`、`UPDATE`、`DELETE`、`REPLACE`、DDL、`CALL`、`DO`、`SET`、`HANDLER`、`LOCK`、`SELECT ... INTO OUTFILE`、`INTO DUMPFILE`、`INTO` 变量、`FOR UPDATE`、`LOCK IN SHARE MODE`、`LOAD_FILE`。解析失败即拒绝。

每条连接在执行语句前把本会话设为事务只读（`transaction_read_only`）。读写账号、甚至管理账号，在这个会话里执行写语句也会被 MySQL 拒绝。本服务不执行 `SET GLOBAL read_only`。

### Mongo

只允许 `find`、`aggregate`、`count`、`distinct`、`collStats`、`dbStats`、`listCollections`、`listIndexes`、`ping`、`serverStatus`、`currentOp`。`find` 必须带过滤条件。聚合阶段只允许 `$match`、`$project`、`$group`、`$sort`、`$limit`。

拒绝 `insert`、`update`、`delete`、`findAndModify`、`bulkWrite`、`drop`、建索引、`mapReduce`、`eval`，以及聚合里的 `$out`、`$merge`。Mongo 没有「特权账号也写不进去」的会话开关，因此命令名和聚合阶段的白名单就是硬边界。连接器只实现上述读方法，发出前再检查一次。

### Elasticsearch

只发出 `GET`、`HEAD`，以及路径限于 `_search`、`_count` 的 `POST`。其余路径限于集群健康、索引统计和 mapping 读取。

拒绝 `PUT`、`DELETE`、`PATCH`，以及 `_bulk`、`_update`、`_update_by_query`、`_delete_by_query`、`_reindex`、建索引、改别名。API Key 即使具备写权限，这些请求也不会发出。

### Redis

命令白名单：`PING`、`GET`、`MGET`、`STRLEN`、`EXISTS`、`TYPE`、`TTL`、`PTTL`、`SCAN`、`HGET`、`HMGET`、`HLEN`、`HSCAN`、`LLEN`、`LRANGE`、`SCARD`、`SMEMBERS`、`ZCARD`、`ZRANGE`、`INFO`、`SLOWLOG GET`、`DBSIZE`、`MEMORY USAGE`。列表、集合、有序集合的返回条数受该目标的上限约束。

其余命令一律拒绝，包括 `SET`、`DEL`、`GETSET`、`GETDEL`、`FLUSHALL`、`FLUSHDB`、`CONFIG`、`DEBUG`、`EVAL`、`EVALSHA`、`SCRIPT`、`KEYS`、`SORT`、`MIGRATE`、`RESTORE`、`ACL`、`SHUTDOWN`、`SUBSCRIBE`。Redis 主库不会因为会话设置而拦住一个有写权限的账号，所以未列入白名单的命令在客户端就被丢弃，不会发送。

### GitLab

只发 `GET`：搜代码、读文件、blame、读提交和流水线状态。创建问题、评论、合并请求、触发流水线、改文件、改项目设置都不会发出。Token 即使是完整的 `api` 权限也一样。

### RabbitMQ

Management API 只发 `GET`，读取队列深度、消费者数量、未确认数和连接摘要。拒绝 purge、发布、ack 和修改策略。不使用会把消息从队列中取走的 AMQP `basic.get` 和 `basic.consume`。

### Kafka

只使用描述类管理接口，以及按分区和 offset 的有限拉取。拉取使用 assign 和 seek，不加入已有消费组，不提交 offset。代码路径里不创建生产者。拒绝创建或删除 topic、修改配置、删除记录、改写消费组 offset。

### CLS

只调用检索和只读描述：搜索日志、取一条日志的上下文、列出已授权主题。拒绝上传日志、删除或修改主题、创建或删除导出任务。

## 各系统要配什么

每一项目标都有这些公共项：显示用的类型、唯一名称、启用开关、超时（默认 15 秒）、单次返回上限（默认 100 行或 100 KB，先触达者为准）。下面是各类型额外字段。密钥与范围分开写。范围只缩小可读边界，不能把「绝对只读」放宽。账号可以是读写账号，调用时仍由闸门截住写操作。

### MySQL

- 主机、端口、用户、密码、默认数据库
- 允许的数据库列表。空列表表示只允许默认数据库
- 查询强制补上 `LIMIT`，并设置语句执行超时
- 语句种类、会话只读见「绝对只读」

### Mongo

- URI，或主机、端口、用户、密码、`authSource`
- 允许的数据库列表
- `find` 必须带过滤条件，空条件视为扫全表并拒绝
- 聚合设置 `maxTimeMS`。允许的阶段和写命令的拒绝见「绝对只读」

### Elasticsearch

- 地址列表、用户名与密码或 API Key
- 允许的索引列表。`_all` 和单独的 `*` 不在可配置范围内
- 搜索的 `size` 不超过该目标的返回上限
- 允许的 HTTP 方法和路径见「绝对只读」

### Redis

- 主机、端口、密码、DB、是否 TLS
- 可选的 key 前缀限制。前缀之外的 key 不读
- `SCAN` 带 `COUNT` 上限。列表、集合、哈希、有序集合的返回条数受该目标上限约束
- 命令白名单见「绝对只读」

### GitLab

- 实例地址、私人 Token
- 允许的项目路径列表。列表之外的项目不读
- 调用只发 `GET`，见「绝对只读」。Token 可以是范围更大的 `api`，写请求仍然不会发出

### RabbitMQ

- Management HTTP 地址、用户、密码、vhost
- 允许的 vhost。列表之外的 vhost 不读
- 只通过 Management API 的 `GET` 查看队列和连接，见「绝对只读」

### Kafka

- bootstrap 地址、安全协议、SASL 用户和密码（如有）
- 允许的 topic 列表。列表之外的 topic 不读、不拉取
- 抽取条数受该目标上限约束。不加入消费组、不提交 offset、不创建生产者，见「绝对只读」

### CLS

- SecretId、SecretKey、地域
- 允许的日志主题列表（日志集 + topic）。列表之外的主题不检索
- 搜索必须带时间窗，默认不超过 1 小时，单次上限 24 小时
- 只调用检索和只读描述，见「绝对只读」

## MCP 工具

工具按排查顺序分三批实现，名称一次定好。参数用排查语义：`target`、服务名、时间窗、trace id、SQL、过滤条件。主机和密钥不是参数。

每条成功结果都带上 target、时间窗或查询摘要、是否截断。截断时明确写出，避免模型把残缺结果当成全量。

第一批，日志对上代码：

| 工具 | 作用 |
|---|---|
| `systems_status` | 哪些目标已启用、最近是否连通 |
| `cls_search` | 按条件搜日志 |
| `cls_context` | 一条日志的前后文 |
| `gitlab_search_code` | 用异常类、日志原文搜仓库 |
| `gitlab_get_file` | 读文件 |
| `gitlab_blame` | 看最近改动 |

第二批，数据面：

| 工具 | 作用 |
|---|---|
| `mysql_query` | 只读 SQL |
| `mysql_explain` | 执行计划 |
| `mysql_processlist` | 当前会话 |
| `mongo_find` | 带条件的查询 |
| `mongo_aggregate` | 受限聚合 |
| `mongo_stats` | 集合统计 |
| `es_search` | 搜索 |
| `es_health` | 集群健康 |
| `es_index_stats` | 索引统计 |
| `redis_get` | 读 key |
| `redis_scan` | 按前缀扫描 |
| `redis_info` | `INFO` |
| `redis_slowlog` | 慢日志 |

第三批，消息面：

| 工具 | 作用 |
|---|---|
| `rabbit_queues` | 队列概览 |
| `rabbit_queue` | 单个队列 |
| `kafka_lag` | 消费组滞后 |
| `kafka_offsets` | topic 位点 |
| `kafka_peek` | 有限抽取，不影响线上消费组 |

另外提供一个 MCP prompt `investigate_error`，把推荐顺序写给模型：先 `cls_search`，再用堆栈或日志原文 `gitlab_search_code`，像慢查询就 `mysql_explain`，像堆积就看队列深度或 `kafka_lag`。关联由模型逐步调用完成，服务端不把八个系统一次扇出。

服务器说明里写上同一套纪律：八个组件绝对只读，且不能由调用方关闭；日志和搜索必须带时间窗；优先使用 trace id；拒绝全表扫描和无上限拉取；结果截断必须向用户说明。

## 没有登录时的边界

登录推迟，不等于把写操作放开。下面这些在第一版就生效，和「谁在调用」无关：

- 模型只能使用已登记且启用的 target
- 八个组件的调用先过「绝对只读」闸门，再受该目标的库、索引、topic、项目范围约束
- 超时、行数、字节数上限
- 审计日志，且不记录密钥
- 工具返回值里不包含连接串和密码
- 默认只监听本机

以后加登录时，同一套检查包住 `/` 和 `/mcp`。审计里的 `anonymous` 换成具体的人。工具实现和表结构保持不动。在那之前，谁能访问这个端口，谁就能查询已登记的线上系统，也能在网页里改凭证。

## 代码结构

实现时按下面拆开。网页、工具、连接器只通过 `ConfigStore` 读写配置，不接触具体数据库驱动。

```
src/dr_panda_mcp/
  server.py            FastMCP、/mcp、服务器说明、custom_route
  web/                 列表与表单
  store/
    protocol.py        ConfigStore 接口
    models.py          三种库共用的表
    repository.py      SQLAlchemy 异步实现
    url.py             解析 DATABASE_URL，补上异步驱动
    migrate.py         启动时迁移到最新版本
  catalog.py           按 name 读取、校验启用、失效排查连接池
  guards/              各组件的只读闸门；未通过则不发请求
  connectors/          八个系统的只读客户端与测试连接
  tools/               排查工具，内部只认 target 名
  prompts.py           investigate_error
data/                  默认的 sqlite 文件，不进 git
```

## 分期

1. **配置台。** HTTP 进程、网页的增删改、启用停用、密钥打码、配置审计、八种类型的表单和测试连接、`/mcp` 上的 `systems_status`。配置库默认 SQLite；同一套迁移和 `ConfigStore` 通过 `DR_PANDA_DATABASE_URL` 用于 MySQL 和 PostgreSQL。测试连接接入只读闸门。这一期结束时，人可以在网页里把连接配好并看到测试结果，三个客户端能连上并看到已登记目标。
2. **日志到代码。** `cls_search`、`cls_context`、GitLab 三个工具、`investigate_error`，以及 CLS 和 GitLab 的闸门与拒绝测试。多数报错在这一期就可以查。
3. **数据面。** MySQL、Mongo、Elasticsearch、Redis 的只读工具，以及各自的闸门和拒绝测试。
4. **消息面。** RabbitMQ 队列，Kafka lag、位点、有限抽取，以及各自的闸门和拒绝测试。
5. **登录。** 给网页和 `/mcp` 加上同一套身份验证，审计改为记到人。在此之前不插入半套 Token。

## 这一版明确不做

- 登录、Token、OAuth，以及按人限制可用 target
- 写库、清队列、改消费位点、发消息、重启服务
- 按目标或全局关闭只读，以及把「执行任意命令」暴露给模型
- 模型可填写的主机、DSN、密码参数
- 独立的前端工程或 MCP 内嵌配置界面
- 把八个系统合成一个自动扇出的「一键排查」工具
- 为 SQLite、MySQL、PostgreSQL 各写一套仓储或手写 SQL
- 在配置库的 SQL 里使用某一种数据库独有的类型或 JSON 运算符
- 把配置库指到业务库，或让排查工具修改配置库
