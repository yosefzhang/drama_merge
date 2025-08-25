from pywebio import start_server
from pywebio.input import *
from pywebio.output import *
from pywebio.pin import *
from pywebio.platform import config
from pywebio.session import set_env
from tornado.netutil import OverrideResolver
from drama_merge_utils import *
import os

def validate_directory(path: str) -> bool:
    """验证目录是否存在且可访问"""
    return path and os.path.exists(path) and os.path.isdir(path)

def format_duration(seconds: float) -> str:
    """将秒数格式化为 mm:ss 格式"""
    minutes = int(seconds // 60)
    seconds = int(seconds % 60)
    return f"{minutes:02d}:{seconds:02d}"

def check_ffmpeg_available() -> bool:
    """检查FFmpeg是否可用"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False

def output_file_list_handler(data: dict, scope: str):
    """显示视频文件列表"""
    clear(scope)
    
    if not validate_directory(data.get('source_dir', '')):
        logging.error(f'源文件目录未指定或不可访问: {data.get("source_dir", "")}')
        return
    
    video_files = get_video_files(data['source_dir'])
    if not video_files:
        put_warning('在指定目录中未找到视频文件', scope=scope)
        return
    
    # 显示文件列表
    with use_scope(scope, clear=True):
        total_size = sum(os.path.getsize(file_path) for file_path in video_files)
        total_size_mb = total_size / (1024 * 1024)
        put_markdown(f'#### 🔍 共发现 {len(video_files)} 个视频文件，总大小: {total_size_mb:.1f} MB', scope=scope)

        if video_files:
            put_markdown(f'#### 源文件目录：`{os.path.dirname(video_files[0])}`', scope=scope)
        else:
            put_markdown(f'#### 源文件目录：`{data.get("source_dir", "")}`', scope=scope)
        with put_scrollable(height=300):
            # 显示加载中信息
            loading_scope = f'{scope}_loading'
            with use_scope(loading_scope, clear=True):
                put_row([
                    put_loading(shape='border', color='primary'),
                    None,
                    put_text('加载文件列表中，请稍候...')
                ], size='auto 10px 1fr')

            table_data = []
            for i, file_path in enumerate(video_files, 1):
                try:
                    filename = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    file_size_mb = file_size / (1024 * 1024)
                    duration = get_video_duration(file_path)
                    duration_str = format_duration(duration)
                    table_data.append([i, filename, f'{file_size_mb:.1f}', duration_str])
                except Exception as e:
                    logging.error(f'处理文件信息时出错: {file_path}, 错误: {str(e)}')
                    table_data.append([i, os.path.basename(file_path), '错误', '错误'])
            
            clear(loading_scope) # 移除加载中信息
            put_table(table_data, header=['序号', '文件名', '大小 (MB)', '时长 (mm:ss)'])

def output_result_handler(results: dict, data: dict, scope: str):
    """显示合并结果"""
    clear(scope)
    table_data = []
    for i, (success, result) in enumerate(results, 1):
        if success:
            output_file = os.path.join(data['output_dir'], result)
            if os.path.exists(output_file):
                try:
                    file_size = os.path.getsize(output_file)
                    file_size_mb = file_size / (1024 * 1024)
                    duration = get_video_duration(output_file)
                    duration_str = format_duration(duration)
                    table_data.append([i, result, f'{file_size_mb:.2f} MB', duration_str, '✅ 成功'])
                except FileNotFoundError:
                    logging.error(f'文件不存在: {output_file}')
                    table_data.append([i, result, 'N/A', 'N/A', '✅ 成功'])
                except Exception as e:
                    logging.error(f'获取文件信息失败: {output_file}, 错误: {str(e)}')
                    table_data.append([i, result, 'N/A', 'N/A', '✅ 成功'])
            else:
                table_data.append([i, result, 'N/A', 'N/A', '✅ 成功'])
        else:
            table_data.append([i, 'N/A', 'N/A', 'N/A', f'❌ 失败: {result}'])

    # 显示结果表格
    clear(scope)
    clear('scope_output_preview')
    put_markdown(f'### 🎉🎉🎉 合并完成！共生成 {len(results)} 个文件！', scope=scope)
    put_table(table_data, header=['序号', '视频文件名', '大小 (MB)', '时长 (mm:ss)', '合并结果'], scope=scope)
    put_markdown('---', scope=scope)

def button_click_handler(data: dict, btn_val: str):
    """处理按钮点击事件"""
    logging.info(f"用户点击了 '{btn_val}' 按钮，当前表单数据: {data}")
    
    if btn_val == '执行合并':
        try:
            # 显示加载中效果在popup中
            with popup('正在合并视频'):
                put_row([put_loading(shape='border', color='primary'), None, put_text('正在合并视频，请稍候...')], size='auto 10px 1fr')
                merge_results = merge_videos(data)
            # 关闭加载popup并显示结果
            close_popup()
            output_result_handler(merge_results, data, scope='scope_output_result')
        except Exception as e:
            logging.error(f'合并过程中发生错误: {str(e)}', exc_info=True)
            put_error(f'合并过程中发生错误: {str(e)}', scope='scope_output_result')

    elif btn_val == '刷新文件列表':
        output_file_list_handler(data, 'scope_output_file_list')
    elif btn_val == '检查文件':
        output_file_list_handler(data, 'scope_output_file_list')
        output_tmdb_handler(data, 'scope_output_tmdb')
        output_preview_handler(data, 'scope_output_preview')
    elif btn_val == '自动批量处理':
        auto_batch_process_handler(data)
        
def output_tmdb_handler(data: dict, scope: str):
    """显示TMDB搜索结果"""    
    if not validate_directory(data.get('source_dir', '')):
        logging.error('源文件目录未指定或不可访问')
        return

    show_name = data.get('show_name', '').strip()
    if show_name == '':
        auto_corrected_show_name = data.get('auto_corrected_show_name', '').strip()
        if auto_corrected_show_name == '':
            auto_corrected_show_name = get_show_name_from_dir(data.get('source_dir', ''))
            data['auto_corrected_show_name'] = auto_corrected_show_name

    # 如果 tmdb_api_key 为空，则不进行 TMDB 搜索
    tmdb_api_key = data.get('tmdb_api_key')
    tmdb_proxy_url = data.get('tmdb_proxy_url')
    tmdb_result = None
    if not tmdb_api_key:
        clear(scope)
        with use_scope(scope, clear=True):
            put_warning('TMDB API Key 未提供，跳过 TMDB 搜索。', scope=scope)
        return

    clear(scope)

    with use_scope(scope, clear=True):
        # 显示加载中信息
        loading_scope = f'{scope}_loading'
        with use_scope(loading_scope, clear=True):
            put_row([put_loading(shape='border', color='primary'), None, put_text('加载TMDB信息中，请稍候...')], size='auto 10px 1fr')
            
            show_name = data.get('show_name', '').strip()
            if show_name != '':
                tmdb_result = search_show_in_tmdb(show_name, tmdb_api_key, tmdb_proxy_url)
                if tmdb_result and isinstance(tmdb_result, dict):
                    name = tmdb_result.get('name', '未知')
                    if name != '未知' and name != show_name:
                        logging.info(f"根据 TMDB 搜索结果，该剧名与指定剧名不同，指定剧名：{show_name}，TMDB 搜索结果的剧名：{name}")
            else:
                tmdb_result = search_show_in_tmdb(auto_corrected_show_name, tmdb_api_key, tmdb_proxy_url)
                if tmdb_result and isinstance(tmdb_result, dict):
                    name = tmdb_result.get('name', '未知')
                    if name != '未知' and name != auto_corrected_show_name:
                        auto_corrected_show_name = name
                        data['auto_corrected_show_name'] = name
                        logging.info(f"根据 TMDB 搜索结果，进一步识别剧名为：{name}， auto_corrected_show_name 已更新为：{auto_corrected_show_name}")
                else:
                    tmdb_result = None

            if tmdb_result and isinstance(tmdb_result, dict):
                id = tmdb_result.get('id', 0)
                show_details = get_show_details_from_tmdb(id, tmdb_api_key, tmdb_proxy_url)
                
                # 构建表格数据
                if show_details:
                    table_data = format_table_data_show_details(show_details, tmdb_api_key, tmdb_proxy_url)
                else:
                    put_error("在 TMDB 未找到相关剧集！")
                    return

            else:
                put_error('在 TMDB 未找到相关剧集！', scope=scope)
            clear(loading_scope)  # 清除加载中信息
            
        # 更新预期生成的文件名预览
        output_preview_handler(data, 'main_info_preview_output')
        # 呈现tmdb搜索结果
        if tmdb_result is not None and show_details is not None and credits is not None:
            show_id = tmdb_result.get('id', 0)
            show_name = tmdb_result.get('name', '未知')
            link = f'https://www.themoviedb.org/tv/{show_id}'

            put_row([
                put_image('https://image.tmdb.org/t/p/original/' + tmdb_result.get('poster_path', ''), width='200px', scope=scope),
                None,
                put_column([
                    put_table([[show_name, put_link(link, link, new_window=True)]], header=['剧名', '链接']),
                    None,
                    put_table(table_data, header=['季', '季名', '集数', '首播日期', '演员'])
                ], size='auto 10px auto')
            ], size='auto 20px auto', scope=scope)
        else:
            put_error('在 TMDB 未找到相关剧集！', scope=scope)
        
        put_markdown('---', scope=scope)

def output_preview_handler(data: dict, scope: str = 'scope_output_preview'):
    """显示预期生成的文件名预览"""
    clear(scope)
    clear('scope_output_result')

    if not validate_directory(data.get('source_dir', '')):
        put_error('源文件目录未指定或不可访问', scope=scope)
        return
    
    # 如果输出目录不存在，则尝试创建
    output_dir = data.get('output_dir', '')
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as e:
            put_error(f'无法创建输出目录: {str(e)}', scope=scope)
            return
    
    if not validate_directory(output_dir):
        put_error('输出目录未指定或不可访问', scope=scope)
        return

    # 如果show_name为空，则使用auto_corrected_show_name
    show_name = data['show_name'] if data['show_name'].strip() else data.get('auto_corrected_show_name', '').strip()
    season = data.get('season', '01') or '01'
    episode_str = data.get('episode', '01')
    # Handle case where episode_str might be empty
    if not episode_str:
        episode_str = '01'
    episode_start = int(episode_str)
    
    # 预览文件名
    preview_filename = f"{show_name}_S{season}E{episode_start:02d}.mp4"
    put_markdown(f'### 预期生成文件名：`{preview_filename}`', scope=scope)

def update_data(data: dict, change: dict):
    """更新数据"""
    from drama_merge_utils import CONFIG
    
    data['source_dir'] = pin.source_dir if pin.source_dir else CONFIG.get('defaults', {}).get('source_dir', '')
    data['output_dir'] = pin.output_dir if pin.output_dir else CONFIG.get('defaults', {}).get('output_dir', '')
    data['show_name'] = pin.show_name
    data['season'] = pin.season if pin.season else CONFIG.get('defaults', {}).get('season', '01')
    data['episode'] = pin.episode if pin.episode else CONFIG.get('defaults', {}).get('episode', '01')
    data['tmdb_api_key'] = pin.tmdb_api_key if pin.tmdb_api_key else CONFIG.get('defaults', {}).get('tmdb_api_key', '')
    data['tmdb_proxy_url'] = pin.tmdb_proxy_url if pin.tmdb_proxy_url else CONFIG.get('defaults', {}).get('tmdb_proxy_url', '')
    data['max_duration'] = pin.max_duration if pin.max_duration else CONFIG.get('defaults', {}).get('max_duration', 0)
    data['max_size'] = pin.max_size if pin.max_size else CONFIG.get('defaults', {}).get('max_size', 0)

    if change.get('name') == "source_dir":
        data['auto_corrected_show_name'] = ''
        logging.info(f"用户更新了 source_dir ，重置 auto_corrected_show_name 为空")

def auto_batch_process_handler(data: dict):
    """自动批量处理"""
    parent_source_dir = data.get('source_dir', '')
    if not validate_directory(parent_source_dir):
        put_error('源文件父目录未指定或不可访问', scope='scope_output_result')
        return

    parent_output_dir = data.get('output_dir', '')
    if not validate_directory(parent_output_dir):
        put_error('输出文件父目录未指定或不可访问', scope='scope_output_result')
        return
    
    # 获取所有子目录
    sub_dirs = [os.path.join(parent_source_dir, d) for d in os.listdir(parent_source_dir) if os.path.isdir(os.path.join(parent_source_dir, d))]
    if not sub_dirs:
        put_warning('在指定父目录中未找到子目录', scope='scope_output_result')
        return
    
    for i, sub_dir in enumerate(sub_dirs, 1):
        data['source_dir'] = sub_dir
        data['output_dir'] = parent_output_dir
        
        output_file_list_handler(data, 'scope_output_file_list')
        output_tmdb_handler(data, 'scope_output_tmdb')
        sub_output_dir = os.path.join(data['output_dir'], data.get('auto_corrected_show_name', ''))
        data['output_dir'] = sub_output_dir
        output_preview_handler(data, 'scope_output_preview')

        logging.info(f"正在处理第 {i}/{len(sub_dirs)} 个：{data}")
        
        # 执行合并
        try:
            # 显示加载中效果在popup中
            with popup('正在合并视频'):
                put_row([put_loading(shape='border', color='primary'), None, put_text('正在合并视频，请稍候...')], size='auto 10px 1fr')
                merge_results = merge_videos(data)
            # 关闭加载popup并显示结果
            close_popup()
            output_result_handler(merge_results, data, scope='scope_output_result')
        except Exception as e:
            logging.error(f'合并过程中发生错误: {str(e)}', exc_info=True)
            put_error(f'合并过程中发生错误: {str(e)}', scope='scope_output_result')
        
        data['auto_corrected_show_name'] = ''
        

@config(title="短剧合并工具")
def main():
    """短剧合并工具"""
    setup_logger()
    logging.info("========== 脚本启动 ==========")
    
    # 设置页面环境
    set_env(output_max_width='1280px')

    # 创建布局
    put_scope('scope_tool_name')
    put_scope('scope_input')
    put_scope('scope_opt_btn')    
    put_buttons([
        {'label': '检查文件', 'value': '检查文件', 'color': 'primary'},
        {'label': '执行合并', 'value': '执行合并', 'color': 'success'},
        {'label': '自动批量处理', 'value': '自动批量处理', 'color': 'warning'},
        {'label': '刷新文件列表', 'value': '刷新文件列表', 'color': 'info'}
    ], scope='scope_opt_btn', onclick=lambda btn_val: button_click_handler(data, btn_val))

    with use_scope('scope_output'):
        put_scope('scope_output_preview')
        put_scope('scope_output_result')
        put_scope('scope_output_tmdb')
        put_scope('scope_output_file_list')
    
    put_html('<h1 style="text-align: center;">短剧合并工具</h1>', scope='scope_tool_name')

    # 检查FFmpeg是否可用
    if not check_ffmpeg_available():
        put_error('❌ FFmpeg未找到！请确保已安装FFmpeg并添加到系统PATH。FFmpeg下载地址：https://ffmpeg.org/download.html', scope='scope_output_result')
        return
    
    # 从配置文件中读取默认值
    from drama_merge_utils import CONFIG
    default_src_dir = CONFIG.get('defaults', {}).get('src_dir', '')
    default_output_dir = CONFIG.get('defaults', {}).get('output_dir', '')
    default_season = CONFIG.get('defaults', {}).get('season', '01')
    default_episode = CONFIG.get('defaults', {}).get('episode', '01')
    default_max_duration = CONFIG.get('defaults', {}).get('max_duration', 60)
    default_max_size = CONFIG.get('defaults', {}).get('max_size', 1000)
    default_tmdb_api_key = CONFIG.get('defaults', {}).get('tmdb_api_key', '')
    default_tmdb_proxy_url = CONFIG.get('defaults', {}).get('tmdb_proxy_url', '')
    
    # 创建持久化的输入表单
    with use_scope('scope_input'):
        put_input(name='source_dir', label='工作目录（必填）', placeholder=f'当前默认： {default_src_dir}' if default_src_dir else '例如：C:\\Videos\\MyShow')
        put_input(name='output_dir', label='输出目录（必填）', placeholder=f'当前默认： {default_output_dir}' if default_output_dir else '例如：C:\\Output')

        put_row([
            put_input(name='show_name', label='指定剧名（可选）', placeholder='留空将自动识别剧名'), None,
            put_input(name='season', label='指定剧季', placeholder=f'当前默认： {default_season}'), None,
            put_input(name='episode', label='指定起始剧集', placeholder=f'当前默认： {default_episode}')
        ], size='2fr 40px 1fr 20px 1fr')

        put_row([
            put_input(name='tmdb_api_key', label='TMDB API Key（必填）', placeholder=f'当前默认： {default_tmdb_api_key}' if default_tmdb_api_key else '从TMDB申请'), None,
            put_input(name='tmdb_proxy_url', label='TMDB 代理 URL（可选）', placeholder=f'当前默认： {default_tmdb_proxy_url}' if default_tmdb_proxy_url else '例如：http://127.0.0.1:7890'), None,
            put_input(name='max_duration', label='最大时长限制（分钟）', placeholder=f'当前默认： {default_max_duration}'), None,
            put_input(name='max_size', label='最大体积限制（MB）', placeholder=f'当前默认： {default_max_size}')
        ], size='1fr 20px 1fr 20px 1fr 20px 1fr')

    # 初始化data字典
    data = {
        'source_dir': default_src_dir,
        'output_dir': default_output_dir,
        'show_name': '',
        'season': default_season,
        'episode': default_episode,
        'tmdb_api_key': default_tmdb_api_key,
        'tmdb_proxy_url': default_tmdb_proxy_url,
        'max_duration': default_max_duration,
        'max_size': default_max_size,
        'auto_corrected_show_name': '',
    }
    while True:
        change = pin_wait_change('source_dir', 'output_dir', 'show_name', 'season', 'episode', 'tmdb_api_key', 'tmdb_proxy_url', 'max_duration', 'max_size')
        logging.info(f"pin_wait_change() 检测到变化: {change}")
        update_data(data, change)

if __name__ == '__main__':
    # 启动Web服务器
    start_server(main, port=8080, debug=True, cdn=False, host='0.0.0.0')