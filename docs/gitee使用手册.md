# Git 师生协作完整流程（主干main + 学生派生分支 + 评审合并）
适用场景：教师维护 `main` 主干（存放完整3D查看器插件框架源码），学生Fork/新建分支开发功能，完成后提交合并，教师审核后并入主干。
分两大块：**教师前期仓库准备**、**学生完整操作流程**、**教师审核合并流程**、**冲突处理**、**日常迭代规范**。

## 前置说明两种模式（二选一，推荐模式1 Fork）
### 模式1：Gitee/GitHub Fork 模式（推荐，适合大量学生，互不污染原仓库）
1. 教师持有**源仓库**（main主干，保护分支，禁止学生直接push）
2. 学生点 `Fork` 复制一份到自己账号，本地开发、新建功能分支
3. 学生开发完成提交 `Pull Request(PR)` 给教师源仓库
4. 教师审核代码，通过后合并进main主干

### 模式2：同一仓库内新建分支（小班，学生都有仓库写权限）
师生共用同一个仓库，学生不Fork，直接基于main新建个人开发分支，完成提MR合并。

下面优先讲**最通用、教学最安全的 Fork 完整流程**，附带同仓库分支简化方案。

# 一、教师前期仓库一次性配置（仅做1次）
## 1. 仓库基础设置（GitHub/Gitee通用）
1. 上传完整项目代码到远程仓库，默认分支命名 `main`；
2. 开启**分支保护规则**（关键，防止学生直接篡改主干）：
   - 仓库设置 → 分支保护 → 添加保护分支 `main`
   - 勾选：禁止直接push到main、合并必须审核、PR至少1人评审（教师自己）
   - 关闭main分支强制推送权限，任何人（除教师管理员）无法直接提交代码到main
3. 仓库开启 `Issues`（学生提问、需求提交）、`Pull Request` 功能。

## 2. 教师本地初始仓库（自己的源仓库）
本地拉取、维护主干代码，仅教师能合并PR到main：
```bash
# 1. 克隆自己的源仓库（教师唯一源仓库）
git clone https://gitee.com/你的账号/3d_viewer_framework.git
cd 3d_viewer_framework

# 2. 本地main永远和远程同步，只用来合并学生代码，不直接写业务
git checkout main
git pull origin main
```

# 二、学生完整操作流程（Fork模式，全程7步）
## 步骤1：网页端Fork教师仓库
1. 打开教师仓库链接，右上角点击 `Fork`；
2. 选择自己个人账号，等待复制完成，得到**学生个人副本仓库**；
3. 学生仓库自带完整 `main` 分支，和教师主干当前代码完全一致。

## 步骤2：学生本地克隆自己Fork后的仓库
```bash
# 克隆学生自己的仓库（不是教师源仓库！）
git clone https://gitee.com/学生账号/3d_viewer_framework.git
cd 3d_viewer_framework

# 配置上游源（关键！同步教师主干更新）
git remote add upstream https://gitee.com/教师账号/3d_viewer_framework.git

# 查看远程仓库，确认origin=自己仓库，upstream=教师仓库
git remote -v
```

## 步骤3：同步教师main最新代码（开发前必做，避免后续大量冲突）
每次开发新功能前，拉取教师主干最新框架代码：
```bash
# 1. 切换本地main
git checkout main
# 2. 拉取教师上游最新代码
git pull upstream main
# 3. 同步更新到学生自己远程仓库main
git push origin main
```

## 步骤4：基于main新建独立功能分支（禁止在main写代码）
规范：分支名统一 `dev/姓名_功能名`，例如 `dev/zhangsan_texture_plugin`
```bash
# 基于干净的main新建开发分支
git checkout -b dev/zhangsan_texture_plugin
```
> 所有插件开发、代码修改全部在这个分支操作，不动本地main。

## 步骤5：学生本地开发、提交代码
开发插件/修改代码完成后，分批提交：
```bash
# 查看修改文件
git status
# 添加所有修改
git add .
# 规范提交注释（教学统一格式）
# 格式：【功能】姓名：修改内容
git commit -m "【纹理插件】张三：完成texture插件独立调试入口，修复Qt导入缺失bug"

# 推送到学生自己远程仓库的同名分支
git push origin dev/zhangsan_texture_plugin
```

## 步骤6：网页提交PR（合并请求）给教师主干
1. 打开学生自己的仓库网页，弹出提示：`Compare & Pull Request`，点击；
2. 目标仓库选择**教师源仓库**，目标分支 `main`；
3. 填写PR说明：
   - 开发功能：xxx插件
   - 修改文件：xxx.py
   - 自测情况：可独立调试、main启动正常、无报错
4. 提交PR，等待教师审核。

## 步骤7：教师更新代码后，学生同步新主干（下一次开发前）
教师合并多人代码后，学生本地需要同步最新框架：
```bash
# 切回本地main
git checkout main
# 拉取教师最新代码
git pull upstream main
# 更新学生远程main
git push origin main
# 新建新分支开发下一个功能
git checkout -b dev/zhangsan_light_plugin
```

# 三、教师操作流程（审核、合并学生PR）
## 阶段1：收到学生PR，代码审核
1. 教师仓库网页 → Pull Requests → 打开学生提交的PR；
2. 逐文件查看代码改动：
   - 插件是否符合框架规范、是否破坏core内核、导入是否完整；
   - 是否存在语法错误、运行报错；
3. 两种处理：
   1）代码不合格：评论指出问题，关闭PR/让学生修改后重新push分支，PR自动更新；
   2）代码合格，无冲突：进入合并。

## 阶段2：合并PR到main主干（3种合并方式，教学推荐「Squash and merge」）
1. **Squash and merge（推荐教学）**
   把学生所有提交压缩成1条干净记录并入main，主干历史整洁，无零散提交；
   填写统一合并备注：`合并张三-纹理贴图插件`，确认合并。
2. 合并完成后，学生PR自动关闭。

## 阶段3：教师本地同步最新主干（可选，本地测试验证）
```bash
git checkout main
git pull origin main
# 本地运行main.py验证整体框架正常
python main.py
```

# 四、简化方案：同一仓库内分支开发（小班，无Fork）
适合班级人数少，学生都有仓库读写权限，不用Fork：
## 学生操作
1. 直接克隆教师源仓库
```bash
git clone 教师仓库地址
cd 3d_viewer_framework
git checkout main
git pull origin main
# 新建个人分支
git checkout -b dev/zhangsan_light
# 开发、提交、推送分支到远程
git push origin dev/zhangsan_light
```
2. 网页提交MR（合并请求），目标分支main，教师审核合并。

## 教师操作
仅需审核远程分支MR，合并后删除学生废弃分支即可。

# 五、代码冲突处理（高频问题）
## 场景：学生PR提示存在代码冲突无法自动合并
### 学生本地解决冲突步骤
```bash
# 1. 切回自己开发分支
git checkout dev/zhangsan_texture_plugin
# 2. 拉取教师最新main代码合并到当前分支
git pull upstream main
# 此时出现冲突，VSCode打开冲突文件，手动修改冲突标记<<<<>>>>
# 3. 解决完冲突后重新提交
git add .
git commit -m "解决与主干main代码冲突，适配最新内核"
# 推送到自己远程分支，PR自动刷新冲突消失
git push origin dev/zhangsan_texture_plugin
```

# 六、统一规范（教学强制要求，减少混乱）
## 1. 分支命名规范
学生开发分支：`dev/姓名_功能`
示例：
dev/lisi_light_plugin
dev/wangwu_measure_plugin

## 2. commit提交注释规范
`【模块】姓名：修改内容`
示例：
`【内核】教师：补充插件扫描容错逻辑`
`【光照插件】李四：新增自发光调节复选框`

## 3. 禁止行为
1. 学生禁止直接push代码到main分支；
2. 禁止在main分支本地修改代码；
3. 禁止一次PR提交多个无关功能，一个插件单独一个分支、一个PR；
4. 提交前必须本地运行`python main.py`验证无报错再提交PR。

# 七、完整流程极简总结
## 学生
1. Fork教师仓库 → 本地克隆 + 绑定教师上游仓库
2. 开发前同步教师main最新代码
3. 新建个人功能分支写插件代码
4. 提交推送自己远程分支
5. 提交PR给教师main，等待审核
6. 有冲突本地合并主干代码解决后重新推送

## 教师
1. 提前配置main分支保护，上传基础框架代码
2. 接收学生PR，审核代码规范、运行可用性
3. 合格则压缩合并入main；不合格留言退回修改
4. 定期拉取本地main验证整体项目可正常运行