# CFDEM 安装文档

## 1. 源码准备

```bash
# 备份 ~/.bashrc，防止改错后无法恢复
cp ~/.bashrc ~/.bashrc.bak.$(date +%Y%m%d_%H%M%S)
sudo apt-get install git

cd $HOME
mkdir CFDEM
cd CFDEM
git clone https://github.com/CFDEMproject/CFDEMcoupling-PUBLIC.git

# 使用已验证的稳定版 CFDEM；先检查当前 commit，不一致时再切换
CFDEMCOMMIT=1b78322bf4330bbf8b5277302907488187fd3263
cd $HOME/CFDEM/CFDEMcoupling-PUBLIC
git log -1 --oneline
if [ "$(git rev-parse HEAD)" != "$CFDEMCOMMIT" ]; then
    git checkout "$CFDEMCOMMIT"
fi
# 再次确认 HEAD，应显示 commit 1b78322bf4330bbf8b5277302907488187fd3263
git log -1 --oneline

cd $HOME
mkdir LIGGGHTS
cd LIGGGHTS
git clone https://github.com/CFDEMproject/LIGGGHTS-PUBLIC.git
git clone https://github.com/ParticulateFlow/LPP.git lpp

# 查看 CFDEM 要求的 OpenFOAM 版本
grep "OFversion=" $HOME/CFDEM/CFDEMcoupling-PUBLIC/src/lagrangian/cfdemParticle/cfdTools/versionInfo.H
# 示例输出：word OFversion="6-commit-af7d7f427be78e9b9beb6aceca8fe7d5d4636876";

# 示例：

# CFDEM对应的5版本OF
# word CFDEMversion="commit-1b78322bf4330bbf8b5277302907488187fd3263"
# word CFDEMversion="cfdem-3.8.1";
# word compatibleLIGGGHTSversion="3.8.0";
# word OFversion="5.x-commit-538044ac05c4672b37c7df607dca1116fa88df88";

# 6版本CFDEM与OF兼容有问题
# word CFDEMversion="cfdem-3.8.1";
# word compatibleLIGGGHTSversion="3.8.0";
# word OFversion="6-commit-af7d7f427be78e9b9beb6aceca8fe7d5d4636876";

# 自动解析 OpenFOAM 版本，下载对应版本并切换到匹配 commit
OFVERSION=$(grep -oP 'OFversion="\K[^-]+' $HOME/CFDEM/CFDEMcoupling-PUBLIC/src/lagrangian/cfdemParticle/cfdTools/versionInfo.H)
OFCOMMIT=$(grep -oP 'commit-\K[^"]+' $HOME/CFDEM/CFDEMcoupling-PUBLIC/src/lagrangian/cfdemParticle/cfdTools/versionInfo.H)
echo "OpenFOAM version: $OFVERSION, commit: $OFCOMMIT"

# 将 OFVERSION、OFCOMMIT 写入 ~/.bashrc，后续终端无需重复解析
echo "export OFVERSION=${OFVERSION}" >> ~/.bashrc
echo "export OFCOMMIT=${OFCOMMIT}" >> ~/.bashrc

cd $HOME
mkdir OpenFOAM
cd OpenFOAM
git clone https://github.com/OpenFOAM/OpenFOAM-${OFVERSION}.git
# ThirdParty 仓库仅含编译脚本，不含 Scotch 等第三方源码 tarball，因此后续跳过 ThirdParty 编译
git clone https://github.com/OpenFOAM/ThirdParty-${OFVERSION}.git
cd OpenFOAM-${OFVERSION}
# 切换到与 CFDEM 匹配的 commit，确保版本兼容
# 先检查当前 commit；稳定版应为 538044ac05c4672b37c7df607dca1116fa88df88
git log -1 --oneline
if [ "$(git rev-parse HEAD)" != "$OFCOMMIT" ]; then
    git checkout "$OFCOMMIT"
fi
# 再次确认 HEAD，应显示 commit 538044ac05c4672b37c7df607dca1116fa88df88
git log -1 --oneline
```

本说明固定使用以下已验证组合，编译前必须确认两个仓库的 `HEAD` 与之完全一致：

```text
CFDEMversion="commit-1b78322bf4330bbf8b5277302907488187fd3263"
OFversion="5.x-commit-538044ac05c4672b37c7df607dca1116fa88df88"
```

若已经下载过源码，也应分别进入 `$HOME/CFDEM/CFDEMcoupling-PUBLIC`（重命名后为
`$HOME/CFDEM/CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION`）和
`$HOME/OpenFOAM/OpenFOAM-5.x`，执行 `git log -1 --oneline`。commit 不一致时，先用
`git checkout <正确的完整 commit>` 切换，再重新执行对应的编译步骤；不要继续使用旧的编译产物。

#### 可能的坑
- 不要用 `git://` 协议，用 `https://` 替代。
- 公共仓库 HTTPS clone 无需认证。若被要求输入账号密码，说明仓库不存在或已失效（如 `git clone https://github.com/CFDEMproject/LPP.git lpp` 已失效），请检查仓库地址。
- 官网 LPP 仓库已失效，改用 `ParticulateFlow/LPP` 替代。
- `git-core` 是旧版包名，已被 `git` 替代，直接安装 `git` 即可。

## 2. 依赖安装

```bash
# OpenFOAM 编译依赖
sudo apt-get install build-essential flex bison cmake zlib1g-dev libboost-system-dev libboost-thread-dev libopenmpi-dev openmpi-bin gnuplot libreadline-dev libncurses-dev libxt-dev libscotch-dev libptscotch-dev

# VTK（最低 6.3，推荐 8.0+。WSL 下也需安装：CFDEM 用 VTK 输出 .vtk 文件，Windows 侧 ParaView 读取显示）
VTK_PKG=$(apt-cache search libvtk | grep -oP '^libvtk\d+-dev' | head -1)
echo "Detected VTK package: ${VTK_PKG}"
sudo apt-get install ${VTK_PKG}

# lpp 后处理工具依赖
sudo apt-get install python3-numpy

# PNG 序列转 GIF（pyScript/png_to_gif.py、step5_ani.sh）依赖 Pillow
sudo apt-get install python3-pil

# 验证 Pillow 是否安装成功
python3 -c "from PIL import Image; print('Pillow is available')"
```

#### 可能的坑
- `libvtk7-dev` 在高版本 Ubuntu 上不可用，会报 `Package 'libvtk7-dev' has no installation candidate`。VTK 包名随 Ubuntu 版本不同而变化（如 libvtk7-dev、libvtk9-dev），先用 `apt-cache search libvtk` 查看可用版本再安装。
- VTK 包及其依赖非常庞大，`sudo apt-get install ${VTK_PKG}` 耗时较长，请耐心等待。
- 高版本 Ubuntu 上 `python-numpy` 已不存在，会报 `E: Unable to locate package python-numpy`，改用 `python3-numpy`。
- 执行 `step5_ani.sh` 时若提示“缺少 Pillow”，请安装 Ubuntu 软件包 `python3-pil`。不建议直接向新版 Ubuntu 的系统 Python 执行 `pip install`，否则可能遇到 `externally-managed-environment` 错误。

## 3. 编译

### 3.1 OpenFOAM 编译安装

```bash
# 写入 ~/.bashrc：编译核心数 + 自动加载 OpenFOAM 环境
WM_NCOMPPROCS=$(( $(nproc) / 2 > 8 ? 8 : $(nproc) / 2 ))
echo "Detected $(nproc) cores, using $WM_NCOMPPROCS for compilation"
echo "export WM_NCOMPPROCS=$WM_NCOMPPROCS" >> ~/.bashrc
# 每次打开终端自动 source OpenFOAM 的 bashrc
echo "source \$HOME/OpenFOAM/OpenFOAM-${OFVERSION}/etc/bashrc" >> ~/.bashrc
source ~/.bashrc

# 编译 OpenFOAM（无需 foamSystemCheck，echo 确认即可）
cd $WM_PROJECT_DIR
echo "Entered OpenFOAM directory: $(pwd)"
# ThirdParty 中 scotch 目录名与实际版本可能不一致，用软链接修正
cd $WM_THIRD_PARTY_DIR
ln -sf scotch_6.0.6 scotch_6.0.3
cd $WM_PROJECT_DIR
./Allwmake
```

#### 可能的坑
- `foamSystemCheck` 在某些 OpenFOAM 版本中不存在，没必要执行。只要 `echo $WM_PROJECT_DIR` 有输出，说明环境已就绪，可直接编译。
- `./Allwmake` 报 `can't cd to scotch_6.0.3/src`：ThirdParty 中实际 scotch 版本（如 6.0.6）与 Allwmake 中硬编码的版本号（6.0.3）不一致，用 `ln -sf scotch_6.0.6 scotch_6.0.3` 创建软链接即可。

### 3.2 CFDEM 编译安装

```bash
# 将 CFDEM 文件夹重命名，带上 OpenFOAM 版本号
cd $HOME/CFDEM
mv CFDEMcoupling-PUBLIC CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION

# 写入 ~/.bashrc：CFDEM 环境变量及 LIGGGHTS、LPP 路径
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

# 加载环境并验证
source ~/.bashrc
cfdemSysTest

# 编译 LIGGGHTS 和 CFDEMcoupling
cfdemCompCFDEMall
# 看到 compilation done. 表示编译全部完成

# 快速验证：列出编译好的求解器
ls $CFDEM_PROJECT_DIR/platforms/linux64GccDPInt32Opt/bin/
# 应显示：cfdemPostproc  cfdemSolverIB  cfdemSolverPiso  cfdemSolverPisoSTM  cfdemSolverPisoScalar
# 出现这些求解器说明已安装成功
```

#### 可能的坑

- `cfdemCompCFDEMall` 会依次编译 LIGGGHTS 可执行文件、LIGGGHTS 共享库、CFDEMcoupling 库、求解器和工具，遇到错误会停止。之前手动编译的 LIGGGHTS 不能直接用，需通过 `cfdemCompLIG` 编译为共享库。
- 也可分步编译：`cfdemCompLIG` \ `cfdemCompCFDEMsrc` \ `cfdemCompCFDEMsol` \ `cfdemCompCFDEMuti`，编译日志位于 `$CFDEM_SRC_DIR/lagrangian/cfdemParticle/etc/log`。
- `echo "...">> ~/.bashrc` 多次执行会重复追加，建议执行前检查 `grep -q "WM_NCOMPPROCS" ~/.bashrc` 是否已存在。
- `OFVERSION` 和 `OFCOMMIT` 已存入 `~/.bashrc`，后续步骤可直接使用。
- WSL 下 `$(nproc)` 获取的是宿主 CPU 数，编译时建议预留一些核心给系统，不要全用。

## Q&A

### 1. 高版本 GCC 编译注意事项

使用高版本 GCC 编译 OpenFOAM-5.x 时，需要进行以下兼容性修改。

#### 1.1 修改 PackedListI.H

文件：

`OpenFOAM/OpenFOAM-5.x/src/OpenFOAM/containers/Lists/PackedList/PackedListI.H`

将约第 550 行的：

```cpp
return *this;
```

修改为：

```cpp
return;
```

#### 1.2 注释 Reaction 的 name 接口

在文件：

`OpenFOAM/OpenFOAM-5.x/src/thermophysicalModels/specie/reaction/Reactions/Reaction/ReactionI.H`

注释以下定义：

```cpp
// template<class ReactionThermo>
// inline word& Reaction<ReactionThermo>::name()
// {
//     return name_;
// }
```

同时在文件：

`OpenFOAM/OpenFOAM-5.x/src/thermophysicalModels/specie/reaction/Reactions/Reaction/Reaction.H`

注释对应声明：

```cpp
// inline word& name();
```

### 2. 编译前如何检查 CFDEM 和 OpenFOAM 的 commit？

CFDEM 和 OpenFOAM 必须使用经过验证且相互匹配的 commit。本说明采用的稳定组合为：

```text
CFDEMversion="commit-1b78322bf4330bbf8b5277302907488187fd3263"
OFversion="5.x-commit-538044ac05c4672b37c7df607dca1116fa88df88"
```

编译前分别进入两个源码仓库，使用 `git log -1` 检查当前 `HEAD`：

```bash
# 检查 CFDEM
cd $HOME/CFDEM/CFDEMcoupling-PUBLIC
git log -1 --oneline
git rev-parse HEAD

# 检查 OpenFOAM
cd $HOME/OpenFOAM/OpenFOAM-5.x
git log -1 --oneline
git rev-parse HEAD
```

如果 CFDEM 已按照本文步骤重命名，则进入：

```bash
cd $HOME/CFDEM/CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION
```

两个仓库的完整 commit 必须分别为：

```text
CFDEM:    1b78322bf4330bbf8b5277302907488187fd3263
OpenFOAM: 538044ac05c4672b37c7df607dca1116fa88df88
```

若检查结果不一致，应先切换到正确的 commit：

```bash
# 在 CFDEM 仓库中执行
git checkout 1b78322bf4330bbf8b5277302907488187fd3263

# 在 OpenFOAM 仓库中执行
git checkout 538044ac05c4672b37c7df607dca1116fa88df88
```

切换后再次执行 `git log -1 --oneline` 确认，并重新编译 OpenFOAM、LIGGGHTS 和
CFDEMcoupling。不要继续使用其他 commit 生成的旧编译产物，否则可能出现接口不兼容、
编译失败或运行异常。
