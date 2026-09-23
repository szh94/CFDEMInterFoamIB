/**
 * Optional Chinese for the dashboard, which is written in English throughout.
 *
 * Two kinds of text are handled separately because they come from two places:
 *
 * * The panel's own words (buttons, tabs, toasts, empty states) are English
 *   source strings right here in the components, so the Chinese for them is
 *   keyed by that exact English text -- `ZH_UI`.
 * * The names the backend supplies (parameter labels, tab names, file card
 *   names) arrive as English strings over the API and are keyed by the id they
 *   belong to -- `ZH_PARAM` and friends.  A label is identified by what it
 *   *is*, not by its English wording, so rewording the backend does not
 *   silently drop the Chinese.
 *
 * Either way a missing entry falls back to the English it was given, so the
 * panel is never blank and translation stays a purely additive layer.
 *
 * The parameter and card tables were lifted from the original Chinese
 * parameter list, so they are complete by construction.
 */

export type Lang = "en" | "zh";

/** Values substituted into a `{name}` placeholder. */
export type Vars = Record<string, string | number>;

/** The panel's own text, keyed by the English source string. */
const ZH_UI: Record<string, string> = {
  // -- top bar --
  "CFDEMInterFoamIB · Case dashboard": "CFDEMInterFoamIB · 算例仪表盘",
  "{n} errors": "{n} 项错误",
  "{n} warnings": "{n} 项警告",
  "Checks pass": "校验通过",
  "Preview the diff and write the files": "预览 diff 并写入文件",
  "Apply changes": "参数更新",
  "{n} unwritten": "{n} 项未写入",
  "Discard every unwritten change": "丢弃当前所有未写入的改动",
  "Cancel changes": "取消更新",
  "Restore the files from the last snapshot": "从上一个快照恢复文件",
  "Roll back": "回滚",
  "Switch to English": "切换为英文",
  "Switch to Chinese": "切换为中文",
  "Switch to the light style": "切换为浅色风格",
  "Switch to the default style": "切换为默认风格",
  "Default": "默认",
  "Light": "浅色",

  // -- case selector --
  "No case selected": "未选择算例",
  "All {n} parameters recognized": "{n} 项参数全部识别",
  "{a}/{b} parameters recognized": "已识别 {a}/{b} 项参数",
  "Current": "当前",

  // -- file menu --
  "File": "文件",
  "Switch to another case folder": "切换到另一个算例文件夹",
  "Currently open project": "当前正在打开的项目",
  "Open project": "打开新项目",
  "Choose a detected case": "选择自动识别的项目",
  "No cases were found.": "没有扫描到任何算例。",
  "Browse…": "浏览…",
  "Browse folders in the page": "在页面里逐级浏览文件夹",
  "Check and open": "校验并打开",
  "Relative to {repo}": "相对 {repo}",

  // -- folder browser --
  "Select the case folder": "选择算例文件夹",
  "Repository": "仓库",
  "Repository root": "仓库根目录",
  "Up one level": "上一级",
  "No subfolders here.": "该目录下没有子文件夹。",
  "Case": "算例",
  "Not a case (needs CFD/system/controlDict)": "不是算例（需要 CFD/system/controlDict）",
  "Select this folder": "选择此文件夹",
  "Close": "关闭",

  // -- tabs --
  "There is a consistency error": "存在一致性错误",
  "There is a consistency warning": "存在一致性警告",
  "{n} files": "{n} 个文件",

  // -- group hints --
  "Geometry inspection: the corners, boundary faces and particles the rules read, drawn from the same effective values the metrics compute with. A face is coloured by its patch and carries an arrow along the normal its own corner order gives, so a face wound the wrong way points into the box. The same picture sits small in the sidebar, where it stays put while the tabs move.":
    "几何检视：规则读到的顶点、边界面与颗粒，用与派生指标完全相同的有效值绘制。每个面按其 patch 着色，并沿自身节点顺序给出的法向画一支箭头，因此绕向写反的面会指向盒子内部。同一张图在侧边栏以小图呈现，切换标签时始终留在原处。",
  "Fluid side: mesh size, physical properties (viscosity, density, surface tension, turbulence and gravity), initial water level, parallel decomposition and solver controls. The same quantity is defined in several files, and the panel on the right flags mismatches as you type.":
    "流体侧：网格尺寸、物理参数（黏度、密度、表面张力、湍流与重力）、初始水位、并行分解与求解控制。同一个量在多个文件中重复定义，右侧会实时指出不一致。",
  "Particle side: LIGGGHTS particle properties, the DEM region and the coupling frequency. Wall coordinates get their own card and must match the fluid domain boundary face by face.":
    "粒子侧：LIGGGHTS 的颗粒属性、DEM 区域与耦合频率。壁面坐标单独成卡，须与流体域边界逐面一致。",
  "Coupling side: the coupling interval is typed here and written into the DEM deck's couple_every when you apply, so the particle tab shows that copy read-only and follows this one as you type.":
    "耦合侧：耦合间隔在这里填写，写入时同步到 DEM 输入的 couple_every，因此粒子页那一项只读，并随这里实时跟随。",
  "Run steps: every step*.sh in the case folder, each against what it has already produced on disk. This page only reads the directory -- nothing here runs a script -- so re-check after running a step in WSL.":
    "运行步骤：算例目录下每个 step*.sh，以及它在磁盘上已经产出的东西。本页只读目录、不执行任何脚本；在 WSL 里跑完一步后回到这里重新检查。",

  // -- run steps --
  "Step {n}": "第 {n} 步",
  "{n}/{m} steps complete": "{n}/{m} 步已完成",
  "Re-check": "重新检查",
  "Done": "已完成",
  "Ready to run": "可以运行",
  "Not started": "未开始",
  "Cleaned": "已清空",
  "Artifacts still present": "产物仍在",
  "No check defined for this script": "这个脚本没有对应的检查规则",
  "Present": "存在",
  "Partial": "不完整",
  "Missing": "不在",
  "Checking the scripts…": "正在检查脚本…",
  "No step scripts were found in this case.": "本算例里没有 step 脚本。",
  "Could not check the scripts": "检查脚本失败",

  // -- derived panel --
  "Collapse the derived panel": "收起指标面板",
  "Expand the derived panel": "展开指标面板",
  "Derived metrics and checks": "派生指标与校验",
  "Values recompute as you edit, so cross-file mismatches surface before anything is written.":
    "数值随编辑实时重算，写入前即可发现跨文件不一致。",
  "Computing…": "正在计算…",
  "Mesh geometry": "网格几何",
  "Geometry preview": "几何预览",
  "{n} vertices · {m} faces": "{n} 个顶点 · {m} 个面",
  "Drag to rotate": "拖动旋转",
  "Reset the view": "恢复默认视角",
  "No vertices or faces were read from the mesh card.": "网格卡片里没读到顶点或面。",
  "Fold the preview": "折叠预览",
  "Unfold the preview": "展开预览",
  "Initial water": "初始水盒",
  "Metrics": "指标",
  "All": "全部",
  "Issues only": "仅问题",
  "No metrics have issues": "没有异常指标",
  "No metrics": "暂无指标",
  "Consistency": "一致性",
  "All cross-file consistency checks pass": "跨文件一致性检查全部通过",
  "Drag to reorder": "拖动可调整顺序",
  "Reset order": "恢复默认顺序",
  "Reset the card order to the default": "把卡片顺序恢复为默认顺序",
  "Inactive under the current configuration ({n})": "当前配置下不生效 ({n})",
  "Jump to {label} · {file}:{line}": "跳到 {label} · {file}:{line}",

  // -- recognition notice --
  "{n} parameters could not be recognized in this case (out of {total}; {a} recognized). They are marked Not found in the panel and are never written; use Open file to add on the parameter card to write the missing lines by hand, and the case is re-read once you save.":
    "该算例有 {n} 项参数未能识别（共 {total} 项，已识别 {a} 项）。这些项在面板里标为「无法定位」，不会被写入；用参数卡片上的「打开文件添加」在面板里补上对应行，保存后会自动重新读取。",
  "Files that could not be read: {files}": "读取失败的文件：{files}",
  "…and {n} more": "…另有 {n} 项",
  "Re-read": "重新读取",
  "Re-read the current case's files; unwritten changes are kept": "重新读取当前算例的文件；未写入的改动会保留",

  // -- status bar --
  "{a}/{b} recognized · {c} editable": "已识别 {a}/{b} · {c} 可编辑",
  "{n} unwritten changes": "{n} 项已修改未写入",
  "No unwritten changes": "无未写入改动",
  "Working…": "处理中…",
  "Ready": "就绪",

  // -- parameter panel --
  "This group has no editable parameters.": "该分组没有可编辑参数。",
  "Open {file} in the panel and add the {n} missing entries by hand":
    "在面板里打开 {file}，手动补上这里缺的 {n} 项",
  "Open file to add": "打开文件添加",
  "Open {file} to add": "打开 {file} 添加",
  "This case creates its particles another way; these settings do not apply":
    "本算例用的是另一条颗粒创建路线，这些设置不适用",
  "Unused {n} · {action}": "未使用 {n} 项 · {action}",
  "Show": "显示",
  "Hide": "隐藏",
  "{n} items": "{n} 项",

  // -- parameter field --
  "On": "开",
  "Off": "关",
  "Enabled: switching it off comments the line out": "已启用：关会把这一行注释掉",
  "Off: the line is commented out; switching it on uncomments it and writes the value back":
    "已关：这一行被注释掉了，开可解除注释并写回数值",
  "Suggested range [{lo}, {hi}]": "建议范围 [{lo}, {hi}]",
  "Differs from the same quantity in another file": "与其它文件中的同名取值不一致",
  "Unused: this case takes the other particle-creation route":
    "未使用：本算例走的是另一条颗粒创建路线",
  "Optional: this case leaves the line out and the solver's own default applies":
    "可选：本算例没有写这一行，求解器会用自己的默认值",
  "Optional: this case leaves the line out, so the value shown is the default":
    "可选：本算例没有写这一行，此处显示的是默认值",
  "Not found: matched {n} times (exactly 1 required)": "无法定位：匹配 {n} 次（需恰好 1 次）",
  "On disk: {value} · click to undo this change": "原值 {value} · 点击撤销这项改动",
  "Derived": "自动",
  "Read-only": "只读",
  "Read-only; this parameter is never written": "该参数为只读，不会写入",
  "Inactive": "不生效",
  "Does not apply under the current configuration": "当前配置下该参数不生效",
  "Unused": "未使用",
  "Optional": "可选",
  "Not found": "无法定位",
  "The pattern did not match exactly once, so it cannot be written safely":
    "正则未能恰好命中一次，为安全起见不可写入",
  "Parameters": "参数",
  "The parameters the selected model is written with": "所选模型要用到的参数",
  "{n} rows": "{n} 行",
  "The rows of this table, in the order the file lists them":
    "表格的各行，文件里的排列顺序",
  "Add": "新增",
  "Remove last": "删除末端",
  "Add a row at the end of the table": "在表格末尾新增一行",
  "Take the last row off the end of the table": "删除表格末尾的一行",
  // -- table column headings (a particle's note and its eight numbers, a
  //    block's type, corners, divisions and grading) --
  "note": "备注",
  "diameter": "直径",
  "density": "密度",
  "type": "类型",
  "nodes": "节点",
  "cells": "单元数",
  "grading": "划分方式",
  "grading parameters": "划分参数",
  "patch type": "面类型",
  "patch name": "面名称",
  "patch": "所属面",
  "{n} marker points": "{n} 个标记点",
  "The macros the mesh's corners are built from; unfold to list them":
    "网格角点由这些宏搭建，展开后按宏名罗列",
  "Will be created when you apply": "写入时创建",
  "Not in the file yet; it is written when applied":
    "文件中还没有这一行，执行写入时会一并创建",

  // -- write preview --
  "Write preview": "写入预览",
  "{f} files will change · {n} parameters · nothing written to disk yet":
    "{f} 个文件将改变 · {n} 项参数 · 尚未写入磁盘",
  "Cancel": "取消",
  "Write {n} files": "确认写入 {n} 个文件",
  "These changes were refused (the rest will still be written):":
    "以下改动被拒绝写入（其余改动仍会写入）：",
  "The write is byte-for-byte identical to the files on disk; nothing would change.":
    "写入内容与磁盘上的文件逐字节一致，不会产生任何改动。",
  "Side by side": "并排视图",
  "Unified": "统一视图",

  // -- file editor --
  "line endings": "行尾",
  "{n} lines": "{n} 行",
  "Unsaved": "未保存",
  "Unchanged": "未改动",
  "Save": "保存",
  "Nothing is written until you press Save; a snapshot is taken first, and Roll back in the top bar undoes it.":
    "改动只在点「保存」时写入，写入前会自动存快照，顶栏「回滚」可撤销。",
  "Dismiss": "关闭",

  // -- dialogs --
  "Roll back to the previous snapshot?": "回滚到上一个快照？",
  "This overwrites the current files with the original bytes from the snapshot.\nUnwritten changes are lost as well.":
    "这会用快照中的原始字节覆盖当前文件。\n未写入的改动也会一并丢失。",
  "Reading the case…": "正在读取算例…",
  "No usable case was found.": "未找到可用算例。",
  "A case needs a": "算例需要有",
  ", anywhere on disk. If nothing here matches, browse to one or type its path under File in the top bar.":
    "，位置不限。若这里没有匹配项，可用顶栏「文件」浏览或直接输入路径。",

  // -- toasts --
  "Start-up failed": "初始化失败",
  "Could not open the case": "打开算例失败",
  "Could not open the file": "打开文件失败",
  "No change": "没有变化",
  "Wrote {file}": "已写入 {file}",
  "Byte-identical to the file on disk; nothing changed.": "与原文件逐字节一致，未改动。",
  "Undo it with Roll back in the top bar.": "可在顶栏「回滚」里撤销。",
  "Write failed": "写入失败",
  "{file} changed after it was opened; close it and reopen to edit.":
    "{file} 在打开之后被改过，关掉重开再编辑。",
  "Re-read failed": "重新读取失败",
  "Nothing to change": "没有改动",
  "Change at least one parameter before previewing.": "先修改至少一个参数再预览。",
  "There is nothing to write.": "没有需要写入的内容。",
  "Preview failed": "预览失败",
  "The content matches the files on disk; no bytes were changed.":
    "写入内容与原文件一致，未改动任何字节。",
  "Wrote {n} files": "已写入 {n} 个文件",
  "{n} changes refused": "{n} 项改动被拒绝",
  "The case is being written; try again in a moment.": "算例正在被写入，请稍后重试。",
  "Rolled back {n} files": "已回滚 {n} 个文件",
  "There is no snapshot to roll back to.": "没有可回滚的快照。",
  "Roll back failed": "回滚失败",

  // -- api --
  "Cannot reach the backend: {message}": "无法连接后端：{message}",
};

/** Parameter names, keyed by parameter id. */
const ZH_PARAM: Record<string, string> = {
  "mesh.xco1": "关键标记点",
  "mesh.yco1": "y 轴向标记点",
  "mesh.zco1": "z 轴向标记点",
  "mesh.xco2": "域 x 最大值",
  "mesh.yco2": "域 y 最大值",
  "mesh.zco2": "域 z 最大值",
  "mesh.vertices": "顶点",
  "mesh.blocks": "几何块",
  "mesh.patches": "边界面",
  "mesh.faces": "面清单",
  "mesh.sf.xmin": "初始水盒 x 下/上界",
  "mesh.sf.ymin": "初始水盒 y 下/上界",
  "mesh.sf.zmin": "初始水盒 z 下/上界",
  "mesh.sf.xmax": "初始水盒 x 上界",
  "mesh.sf.ymax": "初始水盒 y 上界",
  "mesh.sf.zmax": "初始水盒 z 上界",
  "mesh.prox": "x|y|z 方向分解",
  "mesh.proy": "y 方向分解",
  "mesh.proz": "z 方向分解",
  "mesh.numberOfSubdomains": "子域总数",
  "mesh.method": "分解方法",
  "run.startTime": "起始/结束时间",
  "run.endTime": "结束时间",
  "run.deltaT": "CFD 时间步",
  "run.writeControl": "写输出控制",
  "run.writeInterval": "写输出间隔",
  "run.purgeWrite": "保留时间目录数",
  "run.writePrecision": "写精度",
  "run.runTimeModifiable": "运行中可改字典",
  "run.adjustTimeStep": "自适应时间步",
  "run.maxCo": "最大 Courant 数",
  "run.maxAlphaCo": "最大界面 Courant 数",
  "run.maxDeltaT": "最大时间步上限",
  "run.nrProcs": "MPI 进程数",
  "run.solverName": "求解器可执行文件",
  "phys.water.transportModel": "水 (第1相流体) 的黏度模型",
  "phys.air.transportModel": "空气 (第2相流体) 的黏度模型",
  // `phys.water.rho` / `phys.air.rho` are deliberately absent: the density box
  // is labelled `rho` in both languages, because that is the keyword the file
  // spells -- the same reason the coefficients carry their own names.
  "phys.sigma": "表面张力",
  "phys.turbulence": "湍流模型",
  "phys.g": "重力",
  "coupling.verbose": "详细输出",
  "coupling.modelType": "耦合模型",
  "coupling.couplingInterval": "耦合间隔 (DEM 步)",
  "coupling.depth": "颗粒搜索深度",
  "coupling.voidFractionModel": "空隙率模型",
  "coupling.locateModel": "定位模型",
  "coupling.meshMotionModel": "网格运动模型",
  "coupling.dataExchangeModel": "数据交换模型",
  "coupling.turbulenceModelType": "湍流模型文件",
  "coupling.IBProps.maxCellsPerParticle": "IB 单颗粒最大单元数",
  "coupling.IBProps.alphaMin": "IB alphaMin",
  "coupling.IBProps.scaleUpVol": "IB 体积放大系数",
  "coupling.voidExp": "IB void 映射流态相关幂指数",
  "coupling.Coe_V_local": "IB 局部速度系数",
  "coupling.Coe_V_global": "IB 全局速度系数",
  "coupling.doDivCor": "散度修正",
  "dem.xmin": "区域 x 最小/最大值",
  "dem.xmax": "区域 x 最大值",
  "dem.ymin": "区域 y 最小/最大值",
  "dem.ymax": "区域 y 最大值",
  "dem.zmin": "区域 z 最小/最大值",
  "dem.zmax": "区域 z 最大值",
  "dem.timestep": "DEM 时间步",
  "dem.outSteps": "DEM dump 间隔 (步)",
  "dem.thermo": "DEM 屏幕打印间隔 (步)",
  "dem.processors": "进程分解",
  "dem.couple_every": "couple_every (DEM 步)",
  "dem.integr": "积分方式",
  "dem.zone_notes": "备注",
  "dem.particles": "颗粒信息",
  "dem.ms.seed": "模板随机种子",
  "dem.ms.atom_type": "atom 类型",
  "dem.ms.density": "密度",
  "dem.ms.nspheres": "簇内球数",
  "dem.ms.ntry": "模板尝试次数",
  "dem.ms.spheres": "球体排列文件",
  "dem.ms.scale": "缩放系数",
  "dem.ms.type": "模板输出类型",
  "dem.ms.dist_seed": "分布随机种子",
  "dem.ms.fraction": "分布体积分数",
  "dem.ms.reg.xmin": "生成区域 x 最小值",
  "dem.ms.reg.xmax": "生成区域 x 最大值",
  "dem.ms.reg.ymin": "生成区域 y 最小值",
  "dem.ms.reg.ymax": "生成区域 y 最大值",
  "dem.ms.reg.zmin": "生成区域 z 最小值",
  "dem.ms.reg.zmax": "生成区域 z 最大值",
  "dem.ms.insert_seed": "插入随机种子",
  "dem.ms.maxattempt": "最大尝试次数",
  "dem.ms.insert_every": "插入频率",
  "dem.ms.orientation": "初始取向",
  "dem.ms.vel": "插入初速度",
  "dem.ms.overlapcheck": "重叠检查",
  "dem.ms.all_in": "必须全部落入区域",
  "dem.ms.region": "插入目标区域名",
  "dem.ms.particles_in_region": "区域内颗粒数",
  "dem.ms.ntry_mc": "蒙特卡洛尝试次数",
  "dem.wall.x1": "x 下/上界",
  "dem.wall.x2": "x 上界",
  "dem.wall.y1": "y 下/上界",
  "dem.wall.y2": "y 上界",
  "dem.wall.z1": "z 下/上界",
  "dem.wall.z2": "z 上界",
};

/**
 * Derived-metric names, keyed by metric id.  A metric is identified by its id
 * rather than by its label because it can be reworded -- and because one id
 * (`mesh.size`) only ever appears when the metric fails, so its wording is not
 * even the same string as the metric it stands in for.
 */
const ZH_METRIC: Record<string, string> = {
  "mesh.size": "域尺寸",
  "mesh.domain": "域尺寸 (x×y×z)",
  "mesh.delta": "单元尺寸",
  "mesh.uniformity": "单元各向同性",
  "mesh.ncells": "单元总数",
  "mesh.cells_per_diameter": "每颗粒直径的单元数",
  "mesh.span": "直径跨越的整数单元数",
  "coupling.period": "耦合周期",
  "coupling.steps_per_period": "每耦合周期的 CFD 步数",
  "coupling.dem_steps_per_period": "每耦合周期的 DEM 步数",
  "run.cfd_steps": "CFD 总步数",
  "run.frames": "输出帧总数",
  "mesh.water_depth": "初始水深与粒子状态",
  "parallel.subdomains": "并行进程数",
};

/**
 * Consistency-finding titles, keyed by `id:level`.  Unlike a metric, one
 * finding id carries two verdicts and words them differently -- "Domain agrees
 * in x" against "Domain mismatch in x" -- so the level is part of the key; the
 * axis, which is part of the id, is spelled out in the Chinese instead of
 * being substituted.  A pair that is not in the table (a rule that changed
 * level, say) falls back to the English title the backend sent.
 */
const ZH_CHECK: Record<string, string> = {
  "domain.x:ok": "域在 x 方向一致",
  "domain.x:warn": "域在 x 方向不一致",
  "domain.y:ok": "域在 y 方向一致",
  "domain.y:warn": "域在 y 方向不一致",
  "domain.z:ok": "域在 z 方向一致",
  "domain.z:warn": "域在 z 方向不一致",
  "setfields.cover.x:ok": "初始水盒覆盖 x 方向",
  "setfields.cover.x:warn": "初始水盒未覆盖完整 x 范围",
  "setfields.cover.y:ok": "初始水盒覆盖 y 方向",
  "setfields.cover.y:warn": "初始水盒未覆盖完整 y 范围",
  "coupling.divisible:ok": "耦合周期能被 CFD 时间步整除",
  "coupling.divisible:error": "耦合周期不能被 CFD 时间步整除",
  "dem.inside:ok": "颗粒初始位于 DEM 区域内",
  "dem.inside:warn": "颗粒初始位于 DEM 区域外",
  "dem.wall_clearance:ok": "颗粒未穿透壁面",
  "dem.wall_clearance:warn": "颗粒穿透壁面",
  "dem.submerged:ok": "颗粒与初始水面",
  "dem.submerged:info": "颗粒与初始水面",
  "run.adaptivestep:info": "自适应时间步已关闭",
};

/**
 * Step-script verdicts, keyed by the check id the backend assigns.  A check is
 * identified by its id rather than by its English title so that rewording the
 * backend does not silently drop the Chinese -- the same rule `ZH_METRIC`
 * follows, and for the same reason.
 */
const ZH_STEP: Record<string, string> = {
  "clean": "清空中间产物",
  "mesh": "建网格与初始场",
  "run": "运行求解器",
  "reconstruct": "重建并行结果",
  "gif": "合成动画 GIF",
  "curve": "绘制 DEM 曲线",
  "unknown": "未识别的脚本",
};

/** Group (tab) names, keyed by group id. */
const ZH_GROUP: Record<string, string> = {
  // The dashboard's own page, not one the backend sends.
  "geometry": "几何检视",
  "fluid": "流体",
  "particle": "粒子",
  "coupling": "耦合",
  "steps": "运行步骤",
};

/** File card names, keyed by repository-relative path. */
const ZH_FILE: Record<string, string> = {
  "CFD/system/blockMeshDict": "网格与几何域",
  "CFD/system/setFieldsDict": "初始场（水盒）",
  "CFD/system/decomposeParDict": "并行区域分解",
  "CFD/system/controlDict": "求解控制",
  "CFD/constant/transportProperties": "黏度、密度与表面张力",
  "CFD/constant/turbulenceProperties": "湍流",
  "CFD/constant/g": "重力",
  "parCFDDEMrun.sh": "并行启动脚本",
  "CFD/constant/couplingProperties": "耦合与浸没边界",
  "DEM/in.liggghts_run": "颗粒场景",
};

/** Card titles a parameter opts out into, keyed by the English title. */
const ZH_CARD: Record<string, string> = {
  "Physical properties": "物理参数",
  "Variables": "变量",
  "Wall settings": "壁面内置平面 wall 设置",
  "Particle type and creation": "颗粒类型与创建设置",
  "Single particle creation": "单粒子创建",
  "Output control": "输出控制",
};

/** Which table a name belongs to; see `Translator.byId`. */
export type NameKind =
  | "param"
  | "group"
  | "file"
  | "card"
  | "metric"
  | "check"
  | "step";

const TABLES: Record<NameKind, Record<string, string>> = {
  param: ZH_PARAM,
  group: ZH_GROUP,
  file: ZH_FILE,
  card: ZH_CARD,
  metric: ZH_METRIC,
  check: ZH_CHECK,
  step: ZH_STEP,
};

/** Substitute `{name}` placeholders, leaving unknown ones alone. */
function fill(text: string, vars: Vars): string {
  return text.replace(/\{(\w+)\}/g, (whole, key: string) =>
    key in vars ? String(vars[key]) : whole,
  );
}

export class Translator {
  constructor(readonly lang: Lang) {}

  /** The panel's own text: Chinese keyed by the English source string. */
  t(en: string, vars?: Vars): string {
    const text = this.lang === "zh" ? ZH_UI[en] ?? en : en;
    return vars ? fill(text, vars) : text;
  }

  /** A name the backend supplied: Chinese keyed by the id it belongs to. */
  byId(kind: NameKind, id: string, fallback: string): string {
    if (this.lang !== "zh" || !id) return fallback;
    return TABLES[kind][id] ?? fallback;
  }
}

/** Narrow an arbitrary stored/queried value to a language, defaulting to English. */
export function pickLang(raw: string | null | undefined): Lang {
  return raw === "zh" ? "zh" : "en";
}
