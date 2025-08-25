# 短剧视频合并工具

基于pywebio开发的短剧视频合并工具，python代码实现核心逻辑，FFmpeg用于视频合并，使用Pywebio构建Web界面。
可Docker部署，Dockerfile默认会集成FFmpeg。

## 功能介绍

短剧的每一集时长基本是3分钟左右，且剧集数很多，同时TMDB上并不会对短剧的每一集做介绍，因此保持短剧的集数没有太多意义。
集数多时，每一集需要加载，每一集的时长又很短，观看体验较差。因此，我创建这样一个工具，用来合并短而多的短剧视频。

功能特点：
- 按照视频文件命名顺序，合并视频
- 可限制生成视频的体积和时长
- 当未指定短剧的剧名时，工具将根据视频的目录名称进行自动匹配，并尝试在TMDB上搜索，呈现搜索结果
- 提供Web界面
- 可Docker部署

## 使用方法

### 方法一：直接运行

1. 安装Python依赖：
```bash
pip install -r requirements.txt
```

2. 安装FFmpeg：
   - Windows: 下载FFmpeg并添加到系统PATH
   - Linux: `sudo apt install ffmpeg`
   - macOS: `brew install ffmpeg`

3. 运行Web服务器：
```bash
python drama_merge_tool.py
```

4. 打开浏览器访问：`http://localhost:8080`

### 方法二：使用Docker（推荐）

1. 确保已安装Docker和Docker Compose

2. 克隆仓库
```bash
git clone https://github.com/yosefzhang/drama_merge_tool.git
```

3. 构建Docker镜像：
```bash
cd drama_merge_tool
sh ./docker/build_docker_image.sh
```
预期生成镜像：drama_merge_tool:latest

4. 运行Docker容器：
```bash
docker-compose -f docker/docker-compose.yml up -d
```

5. 访问应用：`http://localhost:8080`

## 配置参数解释

### 在Web界面中填写：
   - **工作目录**：包含视频文件的目录路径（必选）
   - **输出目录**：合并后文件的保存目录（必选）
   - **指定剧名**：剧名（可选，留空将根据目录名自动识别剧名）
   - **指定剧季**：季数（可选，默认为01）
   - **指定剧集**：集数（可选，默认为01）

### 输出格式

合并后的文件命名格式：`{剧名}_S{季数}E{集数}.mp4`

例如：`我的剧_S01E01.mp4`

### 注意事项
1. 请将同属于一个短剧的视频文件放在一个目录中，并按照电视剧集命名视频文件。
2. 脚本会自动识别目录名作为剧名，如果目录名无法识别，请手动指定剧名。
3. 所有的配置都存放在config.yaml文件中，用户可以根据需要修改配置。前台输入的配置并不会保存到config.yaml中，如需保存，可以修改config.yaml中的default部分的字段，以减少重复性输入。