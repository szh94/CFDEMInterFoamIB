CFDEM是一款用于流固耦合模拟开源软件包。CFDEM经常与OpenFOAM和LIGGGHTS另外两款开源软件一起被提及，这是因为CFDEM是在OpenFOAM和LIGGGHTS所提供的软件框架之上构建的。三款软件的主要源代码均由C++语言编写。以下称为COOL三件套，为什么两个O呢，是从OpenFOAM里面拿了两个。同时这也让软件听起来很酷不是吗。

互联网上关于三件套的安装教程有很多。不过存在几个问题，一个是介绍的CFDEM安装版本老旧，可能不适用于最新的版本。其次，教程所适用的的系统不一定为Ubuntu16.04甚至不是Ubuntu系统。最后，教程涉及的安装细节可能是直接翻译过来，对一些新用户难以避免的坑没有进行说明。因此，特地撰写此教程帮助流固耦合新手学习者来安装此软件。此教程主要翻译自官方安装教程，英文过关的同学可以直接访问官网的安装页面地址：

https://www.cfdem.com/media/CFDEM/docu/CFDEMcoupling_Manual.html#installation


安装前先说一点Ubuntu系统的东西，因为有一些只用过Windows软件的同学可能对此不熟悉。

首先是Ubuntu系统的配置问题。修改Ubuntu系统中的软件配置往往是通过直接修改某一个文本文件实现的，而在windows端，修改配置往往会有一个用户界面。比如安装一些软件需要添加环境变量(可以理解为全局变量)，windows端常见的操作是，高级系统设置->环境变量->添加自己需要的。这应该是很多人唯一知道的windows端添加环境变量的方式

图片

而在Ubuntu端，添加环境变量的方式主要为，打开一个特定文件，添加以下语句：



export PATH=$PATH:/path/to/your/dir
Ubuntu中的环境变量储存在一个名字为PATH的变量中通过上述命令可以把

/path/to/your/dir这个路径追加到PATH中。这是Windows端与Ubuntu端习惯操作的显著不同。我们在编译过程中，也经常需要手动修改一些文档来进行设置，而非windows端常见的安装软件那样一直点下去就可以了。



闲言少叙，进入安装步骤。

1.编译安装前的准备步骤



这一部主要准备程序安装所依赖的部分。Windows端安装软件往往是执行某一个exe文件，一路点下去，用户不需要关心细节。但是在Ubuntu端，出了类似的安装方法。第二种安装方法为源码编译的安装方法，即用户自行编译源代码，生成可执行程序。三件套的安装推荐全部使用源码编译安装方式。这里用全部，是因为OpenFOAM也可以通过非用户手动编译的的方式进行安装。



源码编译安装中，一个重要问题是当前的的源码依赖于一些基本的工具。但是Ubuntu系统端默认是没有安装的，这就需要用户手动安装这些依赖工具，也称为依赖项的部分。



1.1安装git-core

sudo apt-get install git-core
这一步用来安装git工具。可以理解为git是一个用来从一个叫github的地方下载代码的工具，三件套的源代码都位于github上

官网中提到，在教程中用git协议传输文件。如果Internet连接关闭了端口9418，请使用git clone命令切换到"https://"而不是"git://"。意思是说有些地方(比如一些远程服务器）无法使用git开头的地址来拉取代码，可以换成https开头的网址形式。



1.2 从github获取三件套源代码

进入终端，使用以下命令

cd $HOME
mkdir CFDEM
cd CFDEM
git clone git://github.com/CFDEMproject/CFDEMcoupling-PUBLIC.git
上述命令在用户的$HOME路径下创建了名为CFDEM的文件夹，然后进入CFDEM文件夹，获取github上的CFDEM源代码。也可以从浏览器直接进入网址：github.com/CFDEMproject/CFDEMcoupling-PUBLIC。手动下载源代码并放在相应的路径位置

图片

类似的，创建LIGGGHTS文件夹并下载源码：



cd $HOME
mkdir LIGGGHTS
cd LIGGGHTS
git clone git://github.com/CFDEMproject/LIGGGHTS-PUBLIC.git
官网还提供了LIGGGHTS后处理程序，同样下载到上边的LIGGGHTS路径下，不要搞错路径。下载方式如下：

git clone git://github.com/CFDEMproject/LPP.git lpp
注意上边的命令与之前的git命令的不同之处在于，上边命令末尾有一个lpp。这个意思是把下载下来的文件夹名字修改为lpp。因为默认的名字是LPP。这个修改比较重要，之后的相关路径都是用的小写的lpp。这个程序的本质是一段python程序，主要用于处理liggghts结果数据，所以这个程序不需要后续编译，只要安装了python的依赖库numpy就可以了。后续介绍numpy的安装。

1.3 下载正确的的OpenFOAM版本
这一段的意思是三件套要兼容，截至目前兼容的OpenFOAM版本是6（OpenFOAM-6，对应 commit 见文末附录）。官网提供了版本验证方法：

在刚才下载的CFDEM源码包里面，找到位于如下路径的versionInfo.H文件并打开查看：

src/lagrangian/cfdemParticle/cfdTools/versionInfo.H

在上边文件找到word OFversion=字段并查看相应内容如下：

word OFversion="<OF-Release>-commit-<commitHashtag>";
例如当前 CFDEMcoupling 3.8.1 的 versionInfo.H 中为word OFversion="6-commit-af7d7f427be78e9b9beb6aceca8fe7d5d4636876";

就说明OF-Release=6，commitHashtag=af7d7f427be78e9b9beb6aceca8fe7d5d4636876（克隆OpenFOAM-6后，git checkout af7d7f427be78e9b9beb6aceca8fe7d5d4636876 即可）

获取到OF-Release和commitHashtag的值之后，就可以使用如下命令获取正确的OpenFOAM版本源码：

cd $HOME
mkdir OpenFOAM
cd OpenFOAM
git clone git://github.com/OpenFOAM/OpenFOAM-<OF-Release>.git
cd OpenFOAM-<OF-Release>
git checkout <commitHashtag>
主要注意上面的OF-Release和commitHashtag要先用相应的值替换，不要直接就运行。官网还有如下的命令获取ThirdParty，这个主要是包含Paraview软件。

git clone git://github.com/OpenFOAM/ThirdParty-<OF-Release>.git
Paraview是一个用于计算结果显示以及处理的软件，这个官网推荐的Paraview版本不一定好用。这一步用户可以选择之后自行安装好用的Paraview版本。

至此，所需要的源码下载完了



2. 正式编译前的依赖项安装

首先安装以下的依赖项(官网要求对于Ubuntu14.04+版本，本教程在Windows 11 + WSL2 + Ubuntu 24.04下实测通过)

sudo apt-get install build-essential flex bison cmake zlib1g-dev
sudo apt-get install libboost-system-dev libboost-thread-dev 
sudo apt-get install libopenmpi-dev openmpi-bin gnuplot 
sudo apt-get install libreadline-dev libncurses-dev libxt-dev 
sudo apt-get install libscotch-dev libptscotch-dev
官网把所有的用一条命令安装，这里我把他们拆解开来了，作用是一样的。版本更新时，依赖项可能也要新版本。这也是为什么一些旧版本的安装教程不适用了。这里举几个依赖项的例子，比如cmake，用于编译；带有mpi的用于并行计算；gnupplot用于绘图等等。

然后安装vtk

sudo apt-get install libvtk9-dev
vtk很重要，经常容易有关于vtk版本的问题。vtk主要用于一种数据格式处理。软件数据输出，paraview后处理读取数据都要用到此依赖。(注意：老教程用libvtk6-dev，对应Ubuntu16.04；Ubuntu 24.04的源里是libvtk9-dev)

然后是numpy。之前说了numpy主要是lpp所需要的。

sudo apt-get install python3-numpy
(注意：Ubuntu 24.04 的 Python3 对应 python3-numpy 包，老教程的 python-numpy 只适用旧系统)
除了官网的这些，我在安装过程中遇到过一个缺少curl的提示，可以考虑通过如下命令安装

sudo apt-get update
sudo apt install curl
3. 编译安装

3.1 先编译OpenFOAM

其他两个的编译依赖于OpenFOAM，所以先编译OpenFOAM



在编译之前，先添加需要的变量

nano ~/.bashrc
打上述命令通过文本编辑器nano打开~/路径下的.bashrc文件(要尤其注意这里面的点符号)。~/路径即为用户的home路径。(WSL2无图形界面时gedit不可用，用nano代替；文件编辑完后Ctrl+O保存、Ctrl+X退出)打开文档后，在末尾添加如下两行

export WM_NCOMPPROCS=<NofProcs>
source $HOME/OpenFOAM/OpenFOAM-<OF-Release>/etc/bashrc
其中的<NofProcs>表示编译所使用的核数，因为编译可以多核编译以加快编译速度，一般设置为不超过计算机CPU核数。

然后保存并关闭文件。

之后使用如下命令重新载入



source ~/.bashrc
然后进入到正确的编译文件目录，并进行OpenFOAM的编译

cd $WM_PROJECT_DIR
foamSystemCheck
./Allwmake
其中的foamSystemCheck会提示找不到命令，不用管。因为这个是OpenFOAM4版本之前的功能，从5.x起官方源码就没有了(本教程的OpenFOAM-6同样没有)。而上面的./Allwmake就表示运行编译命令了。这个编译可能会很耗时，几十分钟甚至若干小时都有可能。



3.2 编译LIGGGHTS以及CFDEM

CFDEM依赖于LIGGGHTS，所以LIGGHTS编译在前。不过一步步按照官网教程顺序自然就可以了。

类似于OpenFOAM的编译，编译前先设置一些东西



修改CFDEM内CFDEMcoupling-PUBLIC文件夹的名字，如下：

cd $HOME/CFDEM
mv CFDEMcoupling-PUBLIC CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION
打开两个文件，其中一个路径比较短~/.bashrc，另一个路径有点长，是一个名字叫bashrc的文件，跟前一个名字长得有点像(差一个点)，注意不要混淆，复制如下命令执行即可：



nano ~/.bashrc $HOME/CFDEM/CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION/src/lagrangian/cfdemParticle/etc/bashrc
nano一次打开两个文件，用Alt+数字键在两个缓冲区间切换。在长路径的那个CFDEM的bashrc文件中，找到如下区域：

#================================================#
#- source cfdem env vars
export CFDEM_VERSION=PUBLIC
export CFDEM_PROJECT_DIR=$HOME/CFDEM/CFDEMcoupling-$CFDEM_VERSION-$WM_PROJECT_VERSION
export CFDEM_PROJECT_USER_DIR=$HOME/CFDEM/$LOGNAME-$CFDEM_VERSION-$WM_PROJECT_VERSION
export CFDEM_bashrc=$CFDEM_PROJECT_DIR/src/lagrangian/cfdemParticle/etc/bashrc
export CFDEM_LIGGGHTS_SRC_DIR=$HOME/LIGGGHTS/LIGGGHTS-PUBLIC/src
export CFDEM_LIGGGHTS_MAKEFILE_NAME=auto
export CFDEM_LPP_DIR=$HOME/LIGGGHTS/lpp/src
. $CFDEM_bashrc
#================================================#
可以发现CFDEM的bashrc文件中这一块区域每一行前都会有#，因为这是被注释掉的。把这一块复制一下，粘贴到~/.bashrc文件的末尾。当前版本复制上边的代码即可，注意上述代码中的带有#号的行已经是去掉一个#号的结果了，不能再去掉了。这三行就是注释行的作用。在这个过程中，仅仅从CFDEM中的bashrc进行复制并没有对其修改。重复强调不要混淆两个bashrc文件。另外注意到上面的lpp是小写的，与之前将LPP改成lpp对应起来。



改完~/.bashrc，保存并退出。然后对其重新载入：

source ~/.bashrc
cfdemSysTest
cfdemSysTest的作用是进行检查，一般之前步骤完成后就不会有什么问题。中间可能会有一个询问是否创建用户自己的目录，选择是(Y)就可以了。



接下来就是编译LIGGGHTS和CFDEM了。运行如下命令即可

cfdemCompCFDEMall
上面是一步编译完所有部分，也可以使用逐步编译，上边的一步到位实际就是按顺序执行下列四步。

cfdemCompLIG
cfdemCompCFDEMsrc
cfdemCompCFDEMsol
cfdemCompCFDEMuti
注意拼写：第3条是cfdemCompCFDEMsol(M大写，旧教程常误写成小写m的cfdemCompCFDEmsol)；第4条是cfdemCompCFDEMuti(不要误写成cfdenCompCFDEMuti)



3.3验证编译是否成功

验证方法很多

A.报错验证

终端运行命令cfdemLiggghts

报错提示：ERROR: Invalid command-line...(...169)

即表示编译成功

B.检查是否有求解器

进入CFDEM/CFDEMcoupling-PUBLIC-$WM_PROJECT_VERSION/platforms/linux64GccDPInt32Opt/bin 文件夹，看到官方版5个求解器文件，表示编译成功(本教程实测目录为CFDEMcoupling-PUBLIC-6，即$WM_PROJECT_VERSION=6)



4 后续：单独运行LIGGGHTS



通过如上编译生成的LIGGGHTS的可执行文件名字叫lmp_auto，位于LIGGGHTS/LIGGGHTS-PUBLIC/src路径下，可以检查作为是否成功编译LIGGGHTS的依据。如果想单独运行LIGGGHTS进行DEM计算，很多人推荐创建建一个软连接，如下

sudo  ln -s $HOME/LIGGGHTS/LIGGGHTS-PUBLIC/src/lmp_auto /usr/bin/liggghts
软连接可以理解为Windows端的快捷方式。上述命令就是在/usr/bin目录中创建一个名为liggghts的快捷方式指向lmp_auto执行文件。这样用户可以直接在终端输入liggghts来调用lmp_auto程序了。

有一个问题，可不可以不用软连接，而直接执行lmp_auto呢？答案是肯定的，因为如前所说，软连接就是个快捷方式，最终干活的还是lmp_auto。

但是如果不通过上述软连接，直接在终端输入lmp_auto一般会提示找不到命令(除非lmp_auto就在当前路径)。这是为什么呢？原因是Ubuntu只会在预定义的有限的几个位置(就是之前提到的PATH)搜索用户输入的命令，其中就有/usr/bin和当前路径。这也是为什么把liggghts软连接放在/usr/bin中，当前路径在任意位置都找得到他。而LIGGGHTS/LIGGGHTS-PUBLIC/src不再系统默认搜索路径。

那可不可以直接把lmp_auto放在/usr/bin中呢，答案是肯定的，但是这样做并不太好。一个原因是lmp_auto是一个用户执行文件，本身的体量可能很大，这样直接复制进去会占用空间。另一个原因用户可能要经常重新编译生成新的lmp_auto。这样每次重新编译都要同步更新/usr/bin中的执行文件。而建立软连接，可执行文件源发生更新时，软连接会自动连接到新的文件，只要文件的路径以及名字不更改就可以了。



最后祝大家都可以顺利装好COOL三件套图片图片图片

附录：本教程实测的 OF / CFDEM(及LIGGGHTS)版本与 commit

本教程按以下配套版本实测(对应CFDEMcoupling 3.8.1)。官方判断兼容版本的办法仍是查看CFDEM源码里的versionInfo.H：

src/lagrangian/cfdemParticle/cfdTools/versionInfo.H

其内容(3.8.1)为：

word CFDEMversion="cfdem-3.8.1";
word compatibleLIGGGHTSversion="3.8.0";
word OFversion="6-commit-af7d7f427be78e9b9beb6aceca8fe7d5d4636876";

对应的 git commit：

OpenFOAM-6            af7d7f427be78e9b9beb6aceca8fe7d5d4636876
                      (clone 后 git checkout 此 commit)
CFDEMcoupling-PUBLIC  3.8.1   (commit abedb07，tag 3.8.1)
LIGGGHTS-PUBLIC       3.8.0   (commit 3d5c00f2)

clone 好源码后先 git checkout 到上面对应的 commit/tag，再按正文第3节编译即可。