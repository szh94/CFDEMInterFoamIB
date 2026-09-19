# caseDashboard · 算例参数仪表盘

一个本地 Web 界面，用来查看和修改 `single_sphere` 算例里分散在多个文件中的关键参数，
并在**写盘之前**暴露跨文件不一致。

它只做一件事：**改参数**。不编译、不跑求解器、不调用 `blockMesh`，
**一行 `wsl.exe` 都不执行**，也**一个进程都不起**，只碰 Windows 侧的文本文件。

选文件夹也不需要起进程：点「浏览…」打开的是页面里的文件夹浏览器，靠后端一个只读的目录
列表接口（`/api/browse`）逐级走。它只列仓库内的目录，越界一律 403。`selftest` 里有一条
断言盯着「`server/` 下没有任何文件启动进程」这件事。

未识别参数要「手动补一行」时同样不需要外部程序：仪表盘自带一个文件编辑器。

## 为什么需要它

同一个物理量在多个文件里重复定义，改漏一处就会静默出错：

| 物理量 | 重复位置 |
| --- | --- |
| 耦合间隔 | `couplingProperties: couplingInterval` ↔ `in.liggghts_run: couple_every` |
| 并行度 | `decomposeParDict: numberOfSubdomains` ↔ `in.liggghts_run: processors` ↔ `parCFDDEMrun.sh: nrProcs` |
| 域尺寸 | `blockMeshDict` ↔ `setFieldsDict` ↔ `in.liggghts_run` region ↔ LIGGGHTS 壁面 |
| 颗粒是否在水下 | `in.liggghts_run: create_atoms` 的 z ↔ `setFieldsDict: zmax` |

仪表盘把这些一致性检查放在右侧面板里，**每敲一个数字就重算一次**，
不等你写盘就能看到警告。

## 启动

```bash
python caseDashboard/run.py
```

首次运行会自动在 `caseDashboard/web` 下执行 `npm install`（需要 Node.js）。
随后自动打开浏览器。

| 模式 | 命令 | 端口 |
| --- | --- | --- |
| 开发（默认，热更新） | `python caseDashboard/run.py` | Vite `5173` + 后端 `8765` |
| 生产（单端口） | `python caseDashboard/run.py --prod` | 后端 `8765` 直接托管 `web/dist` |

其他参数：`--no-browser` 不自动开浏览器。

### 双击入口

双击 `caseDashboard/start-dashboard.bat`（等价于 `run.py --prod`，控制台输出英文）。
已在运行时会直接打开浏览器跳过去，不会报端口被占用。

`caseDashboard/launcher.html` 是兜底：后端在跑就跳过去，没在跑就提示先双击上面那个 `.bat`。
`file://` 页面拉不起进程，所以它是「再打开一次」的快捷方式，不是启动器。

### 环境要求

- **Python 3.10+**，只用标准库，**不需要 pip install**
- **Node.js 20+**，只作为构建工具，不参与运行时
- **不需要 WSL**，也不需要装有 OpenFOAM / CFDEM 的环境

（「浏览…」用的是 Windows 自带的 `powershell.exe`，不需要额外安装；非 Windows 上这个按钮
会返回 `503`，手输路径照常可用。）

## 界面

三个标签页按物理分面，参数在页内再按来源文件（或独立卡片）分组：

1. **流体** — `blockMeshDict`、`setFieldsDict`、`decomposeParDict`、`controlDict`、`parCFDDEMrun.sh`
2. **粒子** — `in.liggghts_run`，其中壁面单独成一张「壁面 wall 设置」卡片
3. **耦合** — `couplingProperties`

右侧栏分三块：

- **指标** — 单元尺寸、单元总数、cells per particle diameter、CFD 步数、输出帧数、
  耦合周期内的 CFD 步数、水深等。点卡片上的来源标签可跳到对应输入框
- **一致性** — 跨文件校验结果，按 error / warn 排序，展开可看到具体来源行
- **不生效的参数** — 例如 `adjustTimeStep no` 时 `maxCo` / `maxAlphaCo` / `maxDeltaT`
  完全不起作用，这里会列出来

参数**不是白名单**：同一份声明套用到任何算例上，命中一次的是可编辑参数，
一处都对不上的会标成「无法定位」并写明原因（文件读不到 / 一行都没匹配上 / 匹配到多处）。
当有参数没识别出来时，主区顶部会出现一条提示，把它们和原因一起列出来；
算例名下面和底栏也会显示「已识别 N/M 项参数」。

### 打开新项目

顶栏最左侧、「算例名」按钮左边那个按钮用来切换算例文件夹。它列 `/api/cases` 扫描到的算例，
也可以直接手输仓库内路径（相对仓库根或绝对路径都行；反斜杠也认），或者点「浏览…」在页面里
逐级走仓库目录树。

文件夹浏览器（`FolderBrowser.tsx`）有面包屑、「上一级」和当前路径，会把**是算例的目录标出
「算例」**，不是算例的目录只能穿过去、不能选中——判据和手输一样是 `CFD/system/controlDict`。
一次列一级，所以每一级都在后端重新解析一遍。

它取代的是原先那个 Windows 系统文件夹对话框。那个做法有个治不好的毛病：对话框由浏览器
**间接**起出来的进程弹出，而 Windows 只允许前台进程（或它启动的进程）把窗口提到最前，
所以它总是开在浏览器后面——加 owner 窗口、加 topmost 都绕不过这条规则。画在页面里的浏览器
没有这个问题：它就是用户正在看的那个窗口。

### 仓库外的算例

**算例可以在仓库外**。「什么能打开」只剩一条：目录里得有 `CFD/system/controlDict`。算例是
一个目录的性质，跟它被 clone 到哪儿没关系，所以手输路径和「浏览…」都能走出仓库；走出之后
面包屑的起点从「仓库」换成盘符，底部路径行变成琥珀色，仓库本身则作为一个单独的快捷入口
留在面包屑开头，一键回去。

路径的写法随之统一（`app.path_id`）：**在仓库内用仓库相对路径，出了仓库用绝对路径**，两种
情况都只有一个写法，所以出去的字符串就是回来的字符串。算例名 chip 显示的就是这个值。

`/api/cases` 的扫描仍然只在仓库内做——列表给的是仓库里的算例，仓库外的靠浏览或手输到达。

打开失败时**不会**关掉当前算例、也不会丢弃未写入的改动，菜单和输入框都留在原地好让你改。
成功打开后算例名显示规范化的路径，所以粘贴 `D:\...\tutorial\single_sphere` 之后显示
`tutorial/single_sphere`，而在仓库外则原样显示绝对路径。

算例**不按名字匹配**，所以 `tutorial/multi_sphere_fish`（clump 颗粒、脚本名不同）也直接能开：
参数表 94 项它全部识别得到，顶部提示里不会留任何「无法定位」。

路径框右上角的 **浏览…** 直接弹 Windows 的选文件夹对话框（`/api/explorer/pick`），
选完就把路径填进框里并立即打开。**这是唯一能拿到真实绝对路径的方式**——浏览器自带的
文件夹选择器只给得到文件夹名，给不了路径，所以它必须由后端调 PowerShell 的
`Shell.Application.BrowseForFolder` 来完成。

请求会一直挂着直到你答复对话框，所以菜单在那期间显示「等待选择…」；对话框取消不算错误
（不弹提示、输入框保持不变），路径被拒时它照旧留在框里等你改。对话框**可能被挡在浏览器
窗口后面**，找不到它就看一眼任务栏。

### 写入流程

```
改参数 → 右侧实时重算 → 「参数更新」→ 并排 diff → 确认写入
```

- 改动只存在于前端内存，**不写盘**
- 预览是**逐字节**的：并排视图里未变的行必须完全一致。写入只替换值的那个 span，
  行尾的 `//注释`、`&` 续行、CRLF 换行全部原样保留
- 写入前自动把原始字节存进快照，顶栏「回滚」可恢复
- 若预览显示"逐字节一致"，说明这次改动是空操作，不会被写盘

### 子域总数是算出来的

「并行区域分解」卡片里的**子域总数**不可编辑：它就是 `prox × proy × proz`，
面板上标着 `自动`，数值随三个方向实时变化（改 `z 方向分解` 的瞬间就变，不用等写盘）。

写入时服务端自己把这个乘积落到 `decomposeParDict` 的 `numberOfSubdomains` 行，
所以文件永远和三个方向一致，也不会出现「面板显示 8、文件里还是 4」。
显式传来的子域总数一律拒绝并说明原因。顺带的好处是：文件本来就一致时
它是一次 no-op，仪表盘不会为了复述同一个数字去重写字典。

如果 DEM `processors` 或 `parCFDDEMrun.sh` 的 `nrProcs` 没跟上这个乘积，
右侧照旧报「并行度三处不一致」——那些是真正要手工改的地方。

### 未识别的参数：在面板里打开文件自己补

对不上的参数在面板里标「无法定位」，只读。它们的文件卡片标题右侧会多出一个
**打开文件添加** 按钮，点它在**仪表盘内**弹出该文件的编辑器（外观和「写入预览」是同一套：
行号、等宽、深色底），你把缺的那一行补上、点保存即可。

- 按钮只出现在**确实还有未识别项**的那种卡片上
- 编辑器**不调用系统里的任何程序**，也不猜你用什么编辑器；文件内容就是文本本身
- 行尾跟着文件走：文件是 CRLF 就还是 CRLF，只打开不改再保存是逐字节 no-op
- 保存前自动存快照（顶栏「回滚」可撤销），保存后自动重新读取算例，
  补上的那一行会被正常识别、对应参数变为可编辑
- 若文件在你打开之后被别处改过，保存会被拒绝（409）而不是覆盖掉那次改动
- 顶栏提示条里的 **重新读取** 仍然在，用于你在仪表盘之外改了文件的情况

### 壁面的 取消 / 增加

DEM 页的**壁面 wall 设置**卡片里，每个壁面在标签和数值框之间有一对按钮：

- **取消** — 把该壁面所在行整行注释掉（`# fix ... zwalls2 ...`），数值框随即变灰。
  被取消的壁面不在 LIGGGHTS 配置里，因此**不再参与域一致性比对**
- **增加** — 解除该行注释并恢复可编辑
- 注释掉的壁面仍然能读到坐标值，所以「取消 → 增加」是逐字节可逆的，
  中途也不至于丢失原来的数值

## 安全边界

- **只绑 `127.0.0.1`**，不对外暴露
- 路径参数解析后必须是**已存在且含 `CFD/system/controlDict` 的目录**，阻断目录穿越
- **拒绝来自别的站点的请求**：算例可以在整块盘上，而浏览器能访问 `127.0.0.1`，所以不加这条
  的话，你正在浏览的任意网页都能让仪表盘去列你的磁盘、再改它找到的东西。浏览器会给跨站请求
  打标（`Sec-Fetch-Site` / `Origin`），DNS rebinding 则体现在 `Host` 上，这两种头足以把自家
  页面和别人的分开；不是浏览器发来的请求（脚本、探针、e2e）三个头一个都没有，照常放行
- **一个进程都不起**。`selftest` 有一条断言扫 `server/*.py`，任何模块出现 `subprocess.` /
  `os.system` / `Popen(` / `os.startfile` 之类都会失败——之前那个只读的 WSL 环境探测就是这么
  被删掉的，这条断言防它长回来
- 每个参数的正则必须**恰好命中一次**。命中 0 次或多次即标记为不可编辑并显示红色说明，
  这是防止正则误伤的主要护栏
- `couplingProperties` 里 `alphaMin` 出现 4 次、`maxNumberOfParticles` 出现 2 次，
  这些参数用花括号配对定位到 `IBProps { ... }` 等具体块内部，不会改错块
- **写盘永远不超出「算例目录」这一层**，仓库边界和它无关：`case_file` 只认算例目录内确实存在
  的文件（`..` 穿越 403、不存在 404），回滚也只往算例目录里写。它是第二条写盘路径，和参数写入
  一样走 per-case 锁 + 原子写 + 快照，并且会比对读取时的 sha，文件被别处改过就拒绝保存
- 「浏览…」和手输走**同一条**打开逻辑，所以「有 controlDict」这条规则和它的报错只存在于一处

## 自检

```bash
python -m caseDashboard.server.selftest   # 31 项：写入层的字节级保证 + 进程边界
python -m caseDashboard.server.e2e        # 60 项：HTTP 层（暂存一份算例副本，不动 tutorial）
```

`selftest` 针对上面那些保证，其中最关键的是：

- 零改动写入后，七个配置文件与原文件**逐字节相同**
- 把所有参数回写成当前值后，仍然逐字节相同（正则误伤会在这里暴露）
- 改 `writeControl` 后分号之后的 `;//timeStep;//` 仍在
- 改颗粒直径后同一行的 `density` / `vx` / `vy` / `vz` 未动
- CRLF 行尾数量不变，且不产生裸 LF
- 派生指标与 `docs/single_sphere_set.md` 的参考值一致
- 没有任何 schema 条目的 `file` 指向 `system/controlDict.foam`
- 取消一个壁面只加注释前缀，且「取消 → 增加」逐字节回到原文
- 改一个分解方向，`decomposeParDict` 里**恰好两行**变化（方向本身 + 子域总数），
  显式传子域总数被拒；本来就一致时一次 no-op
- 只有 `picker.py` 会起进程；文件夹对话框的脚本经 `-EncodedCommand` 传递（base64 往返一致，
  否则对话框会静默不出现），且只认信号行——取消返回 `None`、非 ASCII 路径不被破坏、
  完全没有信号行时报错而不是把噪音当路径

`e2e` 覆盖只有走 HTTP 才能验证的部分：preview 不落盘、apply/revert 逐字节往返、
越界值被拒、目录穿越与非算例路径被阻断、回写原值是 no-op、`enabled` 开关能穿过
HTTP 层并在文件里留下/去掉注释、子域总数在预览里已按新方向算好且本身不可编辑；
另外它**只读地**打开 `tutorial/multi_sphere_fish`，断言这类没被专门适配的算例能打开、
识别数自洽、每个未识别项都有原因、且它们一概不可编辑。

## 目录

```
caseDashboard/
  run.py                  一键启动（Windows 侧）
  start-dashboard.bat     双击启动（等价于 run.py --prod）
  launcher.html           双击入口页：探测端口，在跑就跳过去
  server/
    app.py                ThreadingHTTPServer + 路由 + 静态托管
    schema.py             Param 声明式定义
    profiles.py           参数声明、面板分组与文件清单（对所有算例通用）
    reader.py             锚定正则读取 → 值 + file:line
    writer.py             定点 span 替换 / 原子写 / diff
    derived.py            派生指标 + 跨文件一致性校验
    picker.py             系统文件夹对话框（全仓库唯一会起进程的地方）
    state.py              per-case 锁 + undo 快照栈
    selftest.py           字节级回归测试
    e2e.py                HTTP 层回归测试
  web/                    Vite + React + TypeScript + Tailwind（构建产物 gitignore）
  .cache/                 快照（gitignore）
```

## 支持别的算例

**不用做任何事就能打开**——`tutorial/multi_sphere_fish` 现在就是直接可用的：
`profiles.py` 里只有一份参数声明，任何含 `CFD/system/controlDict` 的目录套用它。
对不上的项会逐项报「无法定位」并给出原因，不会写错文件。

要让它识别得更多，就往 `ALL_PARAMS` 里加 `Param`——比如 `multi_sphere_fish` 的颗粒是
用 `create_atoms`/`insert` 的另一种写法生成的，加一条对应正则即可；`reader` / `writer` /
前端都不用改。文件清单 `FILES` 由参数声明自动推导，分组 `GROUPS` 是按物理分的，与文件无关。

## API

后端只监听 `127.0.0.1:8765`。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/cases` | 扫描仓库内算例，附各算例识别到的参数数 |
| GET | `/api/case?path=` | 分组、全部参数及来源行、识别情况（`recognition`） |
| POST | `/api/case/preview` | `{path, edits[]}` → diff + 指标 + 校验，**不落盘** |
| POST | `/api/case/apply` | 同上 → 原子写入 + 返回 before/after 摘要 |
| POST | `/api/case/revert` | 从快照恢复 |
| POST | `/api/case/derive` | `{path, edits[]}` → 仅指标与校验，用于实时重算 |
| GET | `/api/browse?path=` | 文件夹浏览器：列一级子目录，标记哪些是算例，附面包屑与上一级 |
| GET | `/api/file?path=&file=` | 一个算例文件的文本（LF + 原行尾约定 + sha），供面板内编辑器使用 |
| POST | `/api/file/save` | `{path, file, text, sha}` → 原子写 + 快照；sha 对不上返回 409 |

`/api/browse` 的 `path` 空串表示仓库根（浏览器就从这里开始），在仓库内是相对路径、出了仓库
是绝对路径，响应里同样用这一种写法把每一级和上一级报回来。它**不校验是不是算例**——浏览本来
就要穿过不是算例的目录——只列一级，`.` 开头的目录与 `node_modules` / `__pycache__` 不列。
打开哪个算例仍由 `resolve_case` 在路径回来时决定，规则只有一处。
