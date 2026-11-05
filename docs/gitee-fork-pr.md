# 核心结论：**只用你1个教师Gitee账号，可以完整走完「Fork→开发分支→提交PR→审核合并」全流程**
Gitee支持**自己Fork自己仓库**，完全模拟学生操作逻辑，所有界面、命令、审核步骤和真实学生提交PR一模一样，适合你自学演练。
唯一小限制：两个仓库（原教师仓+自己Fork副本）都在你同一个账号名下，不影响流程演示。

## 一、前置准备（教师账号操作）
1. 你的主仓库：`gitee.com/你的账号/3d_viewer_framework`（main主干，已上传完整代码、开启分支保护）
2. 全程只用这一个账号登录，不用切换小号、不用第二个手机号。

## 二、完整分步演练（纯单账号，模拟学生全流程）
### 阶段1：教师账号Fork自己的仓库（模拟学生Fork教师仓库）

1. 打开你的原仓库主页；
2. 右上角点击 **Fork** 按钮；
3. 弹窗选择**当前登录的个人命名空间**（就是你自己账号），点击确认；
4. 等待复制完成，自动跳转到 `gitee.com/你的账号/3d_viewer_framework`（这就是「学生Fork后的个人仓库」）。

> 区分两个仓库：
> - 上游原仓（教师源仓库）：`你的账号/3d_viewer_framework`（父仓库，main受保护）
> - Fork副本仓（模拟学生仓库）：同账号下同名仓库，Gitee会自动重命名为 `3d_viewer_framework_1`

### 阶段2：本地克隆「学生Fork副本仓」，配置上游源（模拟学生本地环境）
```bash
# 1. 克隆Fork后的副本仓库（模拟学生自己的远程仓）
git clone https://gitee.com/你的账号/3d_viewer_framework_1.git
cd 3d_viewer_framework_1

# 2. 绑定上游原教师仓库（同步主干最新代码，学生必做步骤）
git remote add upstream https://gitee.com/你的账号/3d_viewer_framework.git

# 校验远程：origin=Fork副本(学生仓)，upstream=原教师主仓
git remote -v
```

### 阶段3：同步主干+新建功能分支（模拟学生开发规范）
```bash
# 1. 同步教师main最新代码
git checkout main
git pull upstream main
git push origin main

# 2. 新建开发分支（模拟学生开发纹理插件）
git checkout -b dev/demo_texture_plugin
```

### 阶段4：修改代码、提交、推送到Fork副本远程（学生提交代码）
修改`plugins/plugin_texture.py`，模拟学生开发改动：
```bash
git status
git add .
git commit -m "【纹理插件】演示账号：补充独立调试入口"
# 推送到自己Fork的副本仓库远程分支
git push origin dev/demo_texture_plugin
```

### 阶段5：网页端提交PR（合并请求，学生提交给教师审核）
1. 打开Fork副本仓库 `3d_viewer_framework_1` 网页；
2. 页面弹出提示：`推送新分支，创建Pull Request`，点击；
3. 配置PR参数（关键）：
   - 目标仓库(base)：**你的原教师主仓库**（父仓）
   - 目标分支(base branch)：`main`
   - 源仓库(head)：当前Fork副本仓
   - 源分支(head branch)：`dev/demo_texture_plugin`
4. 填写PR标题、修改说明，点击**创建Pull Request**。

此时你的原教师仓库 → Pull Requests列表会出现这条待审核PR，和真实学生提交完全一致。

### 阶段6：教师审核、合并PR（你自己操作审核环节）
1. 切换到**原教师主仓库**网页，打开Pull Requests；
2. 查看代码改动、在线预览文件，模拟教师评审：
   - 不合格：评论指出问题，关闭PR；本地修改代码重新push，PR自动刷新；
   - 合格：选择 **Squash and merge（压缩合并，教学推荐）**，确认合并入main；
3. 合并完成后，PR自动关闭，main主干更新学生代码。

### 阶段7：同步主干（模拟学生下次开发前同步代码）
```bash
# 切回本地main
git checkout main
# 拉取教师仓库合并后的最新代码
git pull upstream main
git push origin main
# 新建下一个功能分支开发
git checkout -b dev/demo_light_plugin
```

## 三、单账号演练的2个小注意点
1. Fork后仓库自动加后缀 `_1`，不会覆盖原仓库，两个仓库独立互不干扰；
2. 分支保护规则正常生效：你无法直接push代码到原仓main，只能通过PR合并，完整复现真实班级约束。

## 四、对比双账号方案优劣
### 只用单账号（你现在的需求）
✅ 优点：不用第二个手机号、不用切换登录、一套账号走完所有流程，自学零门槛；
❌ 缺点：页面上两个仓库都是你的名字，少了「学生独立账号」视觉区分，但**Git流程、PR审核逻辑100%一致**，教学演示完全够用。

### 双账号（真实班级场景）
✅ 优点：账号身份区分明显，贴合真实学生场景；
❌ 缺点：需要第二个手机号注册小号，频繁切换登录。

## 五、极简操作总结（你自学演练直接照做）
1. 自己仓库点Fork，生成副本仓；
2. 克隆副本仓，绑定上游原仓；
3. 新建分支改代码，push到副本远程；
4. 发起PR提交给原仓main；
5. 进入原仓审核PR、合并；
6. 同步主干，完成一轮完整Fork+PR协作流程。