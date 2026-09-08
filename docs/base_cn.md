不知不觉，距离上一篇安装教程记录已经过去6年了。

如何安装CFDEM+OpenFOAM+LIGGGHTS(COOL三件套)

这6年里，AI技术发生了翻天覆地的变化。尤其最近，随着Code Agent的发展，很多Coding的问题已经变得非常简单，软件安装的问题难度也跟6年前不可同日而语。相信很多研究者凭借Agent已经可以迅速解决code工程问题。之前的教程内容也显得有些过时。

然而，我发现的我的windows11系统上的Linux子系统WSL现在也变得很好用了。所以我在想，能不能直接用Code Agent，告诉他"在我的WSL配置好CFDEM"，实测下来依然有难度。所以最近又尝试古法安装，依然是参考CFDEM官网基础教程：

CFDEM®coupling Documentation

实测下来依然有一些坑。所以我把这些坑总结了下就下来，并在自己的wsl中完整安装了一遍。理论上，对于OpenFOAM+Agent大佬，完全可以自己跑通。不过针对研究小白，还是希望这篇教程能有所帮助。

闲言少叙，直接开搞。


1. 安装好WSL

Window11下的WSL装好后会有上边的图标，挺可爱的。命令行输入wsl会进入子系统。

可通过以下命令查看默认装好的WSL对应的Ubuntu版本：

```bash
lsb_release -a
```

WSL装好后，相当于有了一台Ubuntu虚拟机。接下来的操作都在WSL的终端里进行。

在正式开始之前先说一点，和上一篇教程一样，三件套的编译过程中会多次修改一个叫 `~/.bashrc` 的文件。这个文件是Ubuntu的环境配置文件，我们每次打开终端时系统会自动读取它，所以把环境变量写到这里面，以后每次打开终端都能直接用。但是在修改之前，强烈建议先备份一下，万一改错了好恢复：

```bash
# 备份 ~/.bashrc，防止改错后无法恢复
cp ~/.bashrc ~/.bashrc.bak.$(date +%Y%m%d_%H%M%S)
```


2. 从github获取三件套源代码

首先要安装git工具。git可以理解为一个从github下载代码的工具，三件套的源代码都放在github上。

```bash
sudo apt-get install git
```

注意，有些老旧教程会写 `sudo apt-get install git-core`，这个 `git-core` 是旧版包名，现在已经被 `git` 替代了，直接用 `git` 就行。如果你已经装过git，系统会提示你已是最新版，不用管。

有了git之后，进入用户主目录，创建文件夹，开始拉代码：

```bash
cd $HOME
mkdir CFDEM
cd CFDEM
git clone https://github.com/CFDEMproject/CFDEMcoupling-PUBLIC.git

# 使用经过验证的稳定版 CFDEM
CFDEMCOMMIT=1b78322bf4330bbf8b5277302907488187fd3263
cd $HOME/CFDEM/CFDEMcoupling-PUBLIC
git log -1 --oneline
if [ "$(git rev-parse HEAD)" != "$CFDEMCOMMIT" ]; then
    git checkout "$CFDEMCOMMIT"
fi
# 再次确认当前 HEAD
git log -1 --oneline
```

上面命令在 `$HOME` 路径下创建了名为CFDEM的文件夹，然后进入CFDEM文件夹，获取github上的CFDEM源代码。这里不能直接使用仓库的最新提交，必须先切换到经过验证的稳定 commit `1b78322bf4330bbf8b5277302907488187fd3263`，再继续后续安装。

类似的，创建LIGGGHTS文件夹并下载源码：

```bash
cd $HOME
mkdir LIGGGHTS
cd LIGGGHTS
git clone https://github.com/CFDEMproject/LIGGGHTS-PUBLIC.git
```

LIGGGHTS还有一个后处理程序叫LPP，本质是一段Python程序，用于处理LIGGGHTS的结果数据。同样下载到LIGGGHTS路径下：

```bash
git clone https://github.com/ParticulateFlow/LPP.git lpp
```

这里有一个坑：官网写的LPP仓库地址 `github.com/CFDEMproject/LPP.git` 已经失效了，现在已迁移到 `ParticulateFlow/LPP`。如果你用老地址去clone，会弹出来让你输账号密码，这其实不是认证问题，而是仓库不存在或失效了，换个地址就行。另外注意命令末尾有一个 `lpp`，这是把下载下来的文件夹重命名为小写的lpp。这个命名很重要，后面CFDEM的默认路径用的就是小写lpp。

源码的最后一部分是OpenFOAM。OpenFOAM和三件套之间有版本对应关系，不能随便装一个版本。CFDEM的源码里已经写好了它需要的OpenFOAM版本，我们可以直接读出来：

```bash
# 查看 CFDEM 要求的 OpenFOAM 版本
grep "OFversion=" $HOME/CFDEM/CFDEMcoupling-PUBLIC/src/lagrangian/cfdemParticle/cfdTools/versionInfo.H
# 稳定版输出：word OFversion="5.x-commit-538044ac05c4672b37c7df607dca1116fa88df88";
```

稳定版 CFDEM 应打印 `word OFversion="5.x-commit-538044ac05c4672b37c7df607dca1116fa88df88"`。这表示需要 OpenFOAM-5.x，并且必须切换到 commit `538044ac05c4672b37c7df607dca1116fa88df88`。当前安装基准不使用 OpenFOAM-6 组合，因为它与此项目存在兼容问题。

本教程固定使用以下经过验证的匹配组合：

```text
CFDEMversion="commit-1b78322bf4330bbf8b5277302907488187fd3263"
OFversion="5.x-commit-538044ac05c4672b37c7df607dca1116fa88df88"
```

我们可以用命令自动解析出这两个关键参数，然后自动下载：

```bash
# 自动解析 OpenFOAM 版本，下载对应版本并切换到匹配 commit
OFVERSION=$(grep -oP 'OFversion="\K[^-]+' $HOME/CFDEM/CFDEMcoupling-PUBLIC/src/lagrangian/cfdemParticle/cfdTools/versionInfo.H)
OFCOMMIT=$(grep -oP 'commit-\K[^"]+' $HOME/CFDEM/CFDEMcoupling-PUBLIC/src/lagrangian/cfdemParticle/cfdTools/versionInfo.H)
echo "OpenFOAM version: $OFVERSION, commit: $OFCOMMIT"

# 将变量存入 ~/.bashrc，后续终端无需重复解析
echo "export OFVERSION=${OFVERSION}" >> ~/.bashrc
echo "export OFCOMMIT=${OFCOMMIT}" >> ~/.bashrc
```

变量解析出来后，就能去下载正确版本的OpenFOAM了：

```bash
cd $HOME
mkdir OpenFOAM
cd OpenFOAM
git clone https://github.com/OpenFOAM/OpenFOAM-${OFVERSION}.git
git clone https://github.com/OpenFOAM/ThirdParty-${OFVERSION}.git
cd OpenFOAM-${OFVERSION}
# 检查并切换到与 CFDEM 匹配的 commit
git log -1 --oneline
if [ "$(git rev-parse HEAD)" != "$OFCOMMIT" ]; then
    git checkout "$OFCOMMIT"
fi
# 再次确认当前 HEAD
git log -1 --oneline
```

这里有两个小提示：一是不要用 `git://` 协议而用 `https://` 替代，有些网络环境封了git协议的端口。二是ThirdParty仓库虽然叫第三方，但里面只有编译脚本，不包含Scotch等工具的源码本身，后面编译的时候会说到怎么处理。

到此，三件套的源码就下载完了。


3. 正式编译前的依赖项安装

源码编译安装有一个重要前提：当前源码依赖一些基本工具，但Ubuntu默认没有装全，需要我们手动安装。首先是OpenFOAM编译所需的一堆依赖：

```bash
sudo apt-get install build-essential flex bison cmake zlib1g-dev libboost-system-dev libboost-thread-dev libopenmpi-dev openmpi-bin gnuplot libreadline-dev libncurses-dev libxt-dev libscotch-dev libptscotch-dev
```

这些依赖各有用处：cmake用于编译管理，带mpi的库用于并行计算，gnuplot用于绘图等等。

然后是VTK。VTK的作用是让CFDEM运行时能直接输出 `.vtk` 格式的数据文件，然后你在Windows上用ParaView打开看结果。WSL下也必须要装，因为它是在编译阶段就需要链接的库：

```bash
VTK_PKG=$(apt-cache search libvtk | grep -oP '^libvtk\d+-dev' | head -1)
echo "Detected VTK package: ${VTK_PKG}"
sudo apt-get install ${VTK_PKG}
```

VTK这里有个常见的坑：不同Ubuntu版本对应的VTK包名不一样。官网写的 `libvtk7-dev` 在高版本Ubuntu上会报 `Package 'libvtk7-dev' has no installation candidate`。上面用 `apt-cache search` 自动查找系统可用的VTK版本，不管是libvtk7-dev还是libvtk9-dev都能自动匹配。另外VTK及其依赖包非常庞大，安装过程会花比较长的时间，耐心等待就行。

最后是LPP后处理工具的依赖numpy：

```bash
sudo apt-get install python3-numpy
```

老教程里写的 `python-numpy` 在高版本Ubuntu上会报 `E: Unable to locate package python-numpy`，因为Python2已经淘汰了，现在统一用 `python3-numpy`。

项目提供的 PNG 序列转 GIF 工具还依赖 Pillow。使用 Ubuntu 软件包安装可以避免新版系统 Python 的 `externally-managed-environment` 错误：

```bash
sudo apt-get install python3-pil
python3 -c "from PIL import Image; print('Pillow is available')"
```


4. 编译安装

4.1 先编译OpenFOAM

其他两个软件的编译都依赖OpenFOAM，所以OpenFOAM先来。

编译之前，需要设置编译时用几个CPU核心。WSL下 `$(nproc)` 获取的是宿主Windows的总CPU核数，不建议全用，留一些给系统。这里取一半核心数，上限不超过8个：

```bash
# 写入 ~/.bashrc：编译核心数 + 自动加载 OpenFOAM 环境
WM_NCOMPPROCS=$(( $(nproc) / 2 > 8 ? 8 : $(nproc) / 2 ))
echo "Detected $(nproc) cores, using $WM_NCOMPPROCS for compilation"
echo "export WM_NCOMPPROCS=$WM_NCOMPPROCS" >> ~/.bashrc
```

然后让每次打开终端时自动加载OpenFOAM的环境变量：

```bash
echo "source \$HOME/OpenFOAM/OpenFOAM-${OFVERSION}/etc/bashrc" >> ~/.bashrc
source ~/.bashrc
```

现在可以进入OpenFOAM目录开始编译了。编译之前需要先处理一个Scotch版本号不匹配的问题。ThirdParty里的Scotch目录名可能与Allwmake脚本中硬编码的版本号不一致（例如实际是scotch_6.0.6而脚本里写的是scotch_6.0.3），用软链接解决：

```bash
cd $WM_PROJECT_DIR
echo "Entered OpenFOAM directory: $(pwd)"
# ThirdParty 中 scotch 目录名与实际版本可能不一致，用软链接修正
cd $WM_THIRD_PARTY_DIR
ln -sf scotch_6.0.6 scotch_6.0.3
cd $WM_PROJECT_DIR
./Allwmake
```

`foamSystemCheck` 在某些 OpenFOAM 版本中不存在，执行时可能会报 `command not found`。无需依赖该命令，只要 `echo $WM_PROJECT_DIR` 有正确输出，说明环境已经就绪。

`./Allwmake` 就是OpenFOAM的编译命令。这个过程非常漫长，从几十分钟到若干小时都有可能，取决于你的电脑配置。如果编译过程中出错停下来，最常见的就是 `can't cd to scotch_6.0.3/src`，按上面说的软链接方法处理就好。

4.2 编译LIGGGHTS和CFDEM

OpenFOAM编译完之后就可以编译LIGGGHTS和CFDEM了。CFDEM依赖于LIGGGHTS，不过官网提供了一条命令一键搞定，不需要手动分先后。

先按CFDEM的惯例，把CFDEMcoupling-PUBLIC文件夹重命名，带上OpenFOAM的版本号：

```bash
cd $HOME/CFDEM
mv CFDEMcoupling-PUBLIC CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION
```

然后添加CFDEM的环境变量。方法是往 `~/.bashrc` 末尾追加下面这一段：

```bash
cat >> ~/.bashrc << EOF

#- source cfdem env vars
export CFDEM_VERSION=PUBLIC
export CFDEM_PROJECT_DIR=\$HOME/CFDEM/CFDEMcoupling-\$CFDEM_VERSION-\$WM_PROJECT_VERSION
export CFDEM_PROJECT_USER_DIR=\$HOME/CFDEM/\$LOGNAME-\$CFDEM_VERSION-\$WM_PROJECT_VERSION
export CFDEM_bashrc=\$CFDEM_PROJECT_DIR/src/lagrangian/cfdemParticle/etc/bashrc
export CFDEM_LIGGGHTS_SRC_DIR=\$HOME/LIGGGHTS/LIGGGHTS-PUBLIC/src
export CFDEM_LIGGGHTS_MAKEFILE_NAME=auto
export CFDEM_LPP_DIR=\$HOME/LIGGGHTS/lpp/src
. \$CFDEM_bashrc
EOF
```

注意上面的 `\` 反斜杠是用来防止 `$` 符号被提前展开的，让这些变量在每次打开终端时才动态获取值。另外前面提到的lpp小写在这里就对应上了。

加载环境并验证：

```bash
source ~/.bashrc
cfdemSysTest
```

`cfdemSysTest` 会检查CFDEM的配置是否正确，中间可能弹出一个询问是否创建用户目录的提示，选择是(Y)即可。

最后一步，编译：

```bash
cfdemCompCFDEMall
```

`cfdemCompCFDEMall` 会依次编译LIGGGHTS可执行文件、LIGGGHTS共享库、CFDEMcoupling库、CFDEMcoupling求解器和CFDEMcoupling工具。遇到编译错误会停下来。当看到终端出现 `compilation done.` 时，就表示编译全部完成了。

这里有一个容易混淆的地方：之前如果手动编译过LIGGGHTS，生成了一个可执行文件，那是不够的。CFDEM需要LIGGGHTS被编译为共享库的形式，只有用 `cfdemCompCFDEMall`（或者单独用 `cfdemCompLIG`）编译出来的才行。

也可以分步编译，哪步出问题就单独重编哪步：

- `cfdemCompLIG` — 仅编译LIGGGHTS
- `cfdemCompCFDEMsrc` — 仅编译CFDEM库
- `cfdemCompCFDEMsol` — 仅编译CFDEM求解器
- `cfdemCompCFDEMuti` — 仅编译CFDEM工具

编译日志都保存在 `$CFDEM_SRC_DIR/lagrangian/cfdemParticle/etc/log` 路径下，出问题的时候可以去翻日志。

编译完后，怎么知道装成功了没有？最快的验证方式是看有没有生成求解器文件：

```bash
ls $CFDEM_PROJECT_DIR/platforms/linux64GccDPInt32Opt/bin/
# 应显示：cfdemPostproc  cfdemSolverIB  cfdemSolverPiso  cfdemSolverPisoSTM  cfdemSolverPisoScalar
```

如果看到上面这些求解器文件名，说明三件套已经全部装好了。


最后几点提醒：

- 整个过程中多次用 `echo "...">> ~/.bashrc` 向文件追加内容，如果脚本跑了多次，可能会重复追加导致混乱。如果重装，建议先检查bashrc里是不是已经有了对应条目。
- `OFVERSION` 和 `OFCOMMIT` 已经存入了 `~/.bashrc`，后面的步骤可以跨终端使用这些变量。
- WSL下编译OpenFOAM确实比较耗时，建议电脑插着电源、不要休眠，让他慢慢跑。


5. Q&A

5.1 高版本 GCC 编译 OpenFOAM-5.x 报错怎么办？

使用高版本 GCC 编译 OpenFOAM-5.x 时，可能需要进行以下两项兼容性修改。

第一项是修改：

`OpenFOAM/OpenFOAM-5.x/src/OpenFOAM/containers/Lists/PackedList/PackedListI.H`

将约第 550 行的：

```cpp
return *this;
```

修改为：

```cpp
return;
```

第二项是在下面两个文件中注释 `Reaction` 的非 const `name()` 接口：

`OpenFOAM/OpenFOAM-5.x/src/thermophysicalModels/specie/reaction/Reactions/Reaction/ReactionI.H`

```cpp
// template<class ReactionThermo>
// inline word& Reaction<ReactionThermo>::name()
// {
//     return name_;
// }
```

`OpenFOAM/OpenFOAM-5.x/src/thermophysicalModels/specie/reaction/Reactions/Reaction/Reaction.H`

```cpp
// inline word& name();
```

5.2 编译前如何检查 CFDEM 和 OpenFOAM 的 commit？

编译前必须分别进入两个源码仓库，检查当前 `HEAD`：

```bash
# CFDEM（重命名前）
cd $HOME/CFDEM/CFDEMcoupling-PUBLIC
git log -1 --oneline
git rev-parse HEAD

# OpenFOAM
cd $HOME/OpenFOAM/OpenFOAM-5.x
git log -1 --oneline
git rev-parse HEAD
```

如果 CFDEM 已按本文步骤重命名，应改为进入：

```bash
cd $HOME/CFDEM/CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION
git log -1 --oneline
git rev-parse HEAD
```

两个仓库应分别输出以下完整 commit：

```text
CFDEM:    1b78322bf4330bbf8b5277302907488187fd3263
OpenFOAM: 538044ac05c4672b37c7df607dca1116fa88df88
```

如果不一致，应在相应仓库内执行：

```bash
# CFDEM
git checkout 1b78322bf4330bbf8b5277302907488187fd3263

# OpenFOAM
git checkout 538044ac05c4672b37c7df607dca1116fa88df88
```

切换后再次执行 `git log -1 --oneline` 确认，并重新编译 OpenFOAM、LIGGGHTS 和 CFDEMcoupling。不要继续使用其他 commit 生成的旧编译产物，否则可能出现接口不兼容、编译失败或运行异常。

祝大家顺利装好COOL三件套！
