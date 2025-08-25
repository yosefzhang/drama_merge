import json
import logging
import os
import subprocess
import re
from typing import Any, Dict, List, Tuple, Optional
import tmdbsimple as tmdb
from user_agents.parsers import TABLET_DEVICE_FAMILIES
import yaml
from pywebio.output import span, style, put_text, put_link

# 读取配置文件
def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', 'config.yaml')
    default_config = {
        'logging': {
            'filename': 'app.log',
            'level': 'INFO',
            'format': '%(asctime)s [%(levelname)s] %(message)s',
            'date_format': '%Y-%m-%d %H:%M:%S'
        },
        'defaults': {
            'season': '01',
            'episode': '01',
            'max_duration': 0,
            'max_size': 0
        },
        'video': {
            'extensions': ['.mp4', '.mkv', '.mov', '.avi', '.flv', '.wmv'],
            'ffprobe_timeout': 10,
            'ffmpeg_timeout': 300,
            'required_metadata': ['width', 'height', 'video_codec']
        }
    }
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            # 确保所有必需的键都存在
            for key in default_config:
                if key not in config:
                    config[key] = default_config[key]
                elif isinstance(default_config[key], dict):
                    for sub_key in default_config[key]:
                        if sub_key not in config[key]:
                            config[key][sub_key] = default_config[key][sub_key]
            return config
    except FileNotFoundError:
        # 如果配置文件不存在，使用默认配置
        print("配置文件未找到，使用默认配置")
        return default_config
    except Exception as e:
        print(f"配置文件加载失败: {e}，使用默认配置")
        return default_config

# 加载配置
CONFIG = load_config()

def setup_logger():
    """设置日志记录器"""
    # 创建文件处理器，将日志写入到data目录的log文件中
    log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data', CONFIG['logging']['filename'])
    
    # 配置日志格式
    formatter = logging.Formatter(
        CONFIG['logging']['format'],
        datefmt=CONFIG['logging']['date_format']
    )
    
    # 创建文件处理器
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(getattr(logging, CONFIG['logging']['level']))
    file_handler.setFormatter(formatter)
    
    # 配置根日志记录器
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, CONFIG['logging']['level']))
    root_logger.addHandler(file_handler)
    
    # 同时输出到控制台
    console_handler = logging.StreamHandler()
    console_handler.setLevel(getattr(logging, CONFIG['logging']['level']))
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

def get_video_files(source_dir: str) -> List[str]:
    """获取目录下的所有视频文件"""
    if not os.path.exists(source_dir):
        return []
    
    video_extensions = tuple(CONFIG['video']['extensions'])
    video_files = []
    
    for filename in os.listdir(source_dir):
        if filename.lower().endswith(video_extensions):
            file_path = os.path.join(source_dir, filename)
            if os.path.isfile(file_path):
                video_files.append(file_path)
    
    # 按文件名排序
    video_files.sort()
    return video_files

def get_video_metadata(file_path: str) -> Dict[str, Any]:
    """获取视频文件的元数据信息"""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 
        'stream=codec_type,width,height,r_frame_rate,codec_name', 
        '-of', 'json', file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CONFIG['video']['ffprobe_timeout'], encoding='utf-8', errors='ignore')
        if result.returncode != 0:
            logging.error(f'ffprobe执行失败: {file_path}, 返回码: {result.returncode}')
            return None
    except subprocess.TimeoutExpired:
        logging.error(f'ffprobe超时: {file_path} (超过{CONFIG["video"]["ffprobe_timeout"]}秒)')
        return None
    except FileNotFoundError:
        logging.error('ffprobe命令未找到，请确保已安装ffmpeg并添加到系统PATH')
        return None
    except Exception as e:
        logging.error(f'获取视频元数据异常: {file_path}, 错误: {str(e)}')
        return None
    
    try:
        data = json.loads(result.stdout)
        streams = data.get('streams', [])
    except json.JSONDecodeError as e:
        logging.error(f'解析ffprobe输出失败: {file_path}, 错误: {str(e)}')
        return None
    
    metadata = {}
    for stream in streams:
        stream_type = stream.get('codec_type')
        if stream_type == 'video':
            metadata['width'] = stream.get('width')
            metadata['height'] = stream.get('height')
            metadata['frame_rate'] = stream.get('r_frame_rate')
            metadata['video_codec'] = stream.get('codec_name')
        elif stream_type == 'audio':
            metadata['audio_codec'] = stream.get('codec_name')
    
    # 过滤掉None值
    metadata = {k: v for k, v in metadata.items() if v is not None}
    
    # 验证关键视频元数据是否完整
    required_fields = CONFIG['video'].get('required_metadata', ['width', 'height', 'video_codec'])
    missing_fields = [field for field in required_fields if field not in metadata]
    if missing_fields:
        logging.warning(f'视频元数据不完整: {file_path}, 缺少字段: {missing_fields}，将使用现有元数据')
    
    return metadata

def get_video_duration(file_path: str) -> float:
    """获取视频文件的时长（秒）"""
    cmd = [
        'ffprobe', '-v', 'error', '-show_entries', 
        'format=duration', '-of', 'default=nw=1', file_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CONFIG['video']['ffprobe_timeout'], encoding='utf-8', errors='ignore')
        if result.returncode != 0:
            logging.error(f'ffprobe执行失败: {file_path}, 返回码: {result.returncode}')
            return 0
    except subprocess.TimeoutExpired:
        logging.error(f'ffprobe超时: {file_path} (超过{CONFIG["video"]["ffprobe_timeout"]}秒)')
        return 0
    except FileNotFoundError:
        logging.error('ffprobe命令未找到，请确保已安装ffmpeg并添加到系统PATH')
        return 0
    except Exception as e:
        logging.error(f'获取视频时长异常: {file_path}, 错误: {str(e)}')
        return 0
    
    try:
        # 解析 "duration=125.248000" 格式的输出
        output = result.stdout.strip()
        if output.startswith('duration='):
            duration_str = output.split('=', 1)[1]
            duration = float(duration_str)
        else:
            # 如果不是键值对格式，直接转换
            duration = float(output)
        return duration
    except ValueError as e:
        logging.error(f'解析视频时长失败: {file_path}, 错误: {str(e)}, 输出: {result.stdout.strip()}')
        return 0
    except Exception as e:
        logging.error(f'获取视频时长时发生未知错误: {file_path}, 错误: {str(e)}')
        return 0

def check_video_parameters_consistency(file_list: List[str]) -> Tuple[bool, str]:
    """检查所有视频文件参数是否一致"""
    if not file_list:
        return True, "无视频文件需要检查"
    
    # 获取第一个视频的元数据作为基准
    base_metadata = get_video_metadata(file_list[0])
    if not base_metadata:
        return False, f'无法获取基准视频元数据: {file_list[0]}'
    
    for file_path in file_list[1:]:
        metadata = get_video_metadata(file_path)
        if not metadata:
            return False, f'无法获取视频元数据: {file_path}'
        
        # 检查关键参数是否一致
        inconsistent = []
        for key in ['width', 'height', 'frame_rate', 'video_codec', 'audio_codec']:
            if key in base_metadata and key in metadata and base_metadata[key] != metadata[key]:
                inconsistent.append(f"{key}: {base_metadata[key]} vs {metadata[key]}")
        
        if inconsistent:
            return False, f'视频参数不一致: {file_path}, {", ".join(inconsistent)}'
    
    return True, "所有视频参数一致"

def merge_videos_ffmpeg(file_list: List[str], output_path: str, show_name: str, 
                       season: str = "01", episode: str = "01") -> Tuple[bool, str]:
    """
    合并视频文件
    
    Args:
        file_list: 要合并的视频文件列表 (已按照文件名顺序排序)
        output_path: 输出文件路径
        show_name: 显示名称
        season: 季数
        episode: 集数
        
    Returns:
        Tuple[bool, str]: (是否成功, 输出文件名或错误信息)
    """
    if not file_list:
        return False, "没有视频文件需要合并"
    
    # 检查视频参数一致性
    params_ok, message = check_video_parameters_consistency(file_list)
    if not params_ok:
        return False, f'视频参数检查失败: {message}'
    
    # 生成输出文件名
    output_filename = f"{show_name}_S{season}E{episode}.mp4"
    full_output_path = os.path.join(output_path, output_filename)
    
    # 确保输出目录存在
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
    
    # 检查输出文件是否已存在
    if os.path.exists(full_output_path):
        return False, f'输出文件已存在: {full_output_path}'
    
    # 创建临时文件列表
    temp_list_file = os.path.join(output_path, 'file_list.txt')
    try:
        with open(temp_list_file, 'w', encoding='utf-8') as f:
            for file_path in file_list:
                # 使用绝对路径并转义反斜杠
                abs_path = os.path.abspath(file_path).replace('\\', '\\\\')
                f.write(f"file '{abs_path}'\n")
        
        # 构建FFmpeg命令
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0', '-i', temp_list_file,
            '-c', 'copy', full_output_path
        ]
        
        # 执行FFmpeg命令
        logging.info(f'开始合并视频: {" ".join(cmd)}')
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CONFIG['video']['ffmpeg_timeout'], encoding='utf-8', errors='ignore')
        
        # 删除临时文件
        os.remove(temp_list_file)
        
        if result.returncode != 0:
            error_msg = f'FFmpeg执行失败: {result.stderr}'
            logging.error(error_msg)
            return False, error_msg
        
        logging.info(f'视频合并成功: {full_output_path}')
        return True, full_output_path
    except subprocess.TimeoutExpired:
        error_msg = f'FFmpeg超时 (超过{CONFIG["video"]["ffmpeg_timeout"]}秒)'
        logging.error(error_msg)
        # 确保删除临时文件
        if os.path.exists(temp_list_file):
            os.remove(temp_list_file)
        return False, error_msg
    except Exception as e:
        error_msg = f'合并视频时发生错误: {str(e)}'
        logging.error(error_msg)
        # 确保删除临时文件
        if os.path.exists(temp_list_file):
            os.remove(temp_list_file)
        return False, error_msg

def merge_videos(data: Dict[str, Any]) -> List[Tuple[bool, str]]:
    """根据时长和体积限制合并视频文件
    
    Args:
        data: 包含以下键的字典:
            - source_dir: 源视频文件目录
            - output_dir: 输出文件目录
            - show_name: 显示名称
            - season: 季数
            - max_duration: 最大时长限制（分钟）
            - max_size: 最大体积限制（MB）
            - episode: 起始集数
            
    Returns:
        List[Tuple[bool, str]]: 合并结果列表
    """
    
    # 从data参数中获取配置
    source_dir = data['source_dir']
    output_dir = data['output_dir']
    # 如果show_name为空，则使用auto_corrected_show_name
    show_name = data['show_name'] if data['show_name'].strip() else data.get('auto_corrected_show_name', '')
    season = data['season']
    # Handle case where max_duration might be empty
    max_duration_str = data.get('max_duration', '0')
    if not max_duration_str:
        max_duration_str = '0'
    max_duration = float(max_duration_str) * 60  # 转换为秒
    
    # Handle case where max_size might be empty
    max_size_str = data.get('max_size', '0')
    if not max_size_str:
        max_size_str = '0'
    max_size = float(max_size_str) * 1024 * 1024  # 转换为字节
    
    # Handle case where episode might be empty
    episode_str = data.get('episode', '01')
    if not episode_str:
        episode_str = '01'
    episode_start = int(episode_str)

    file_list = get_video_files(source_dir)
    if not file_list:
        return [(False, "没有视频文件需要合并")]
    
    results = []
    current_group = []
    current_duration = 0
    current_size = 0
    episode_num = episode_start
    
    # 遍历所有文件
    for file_path in file_list:
        # 获取当前文件的时长和大小
        file_size = os.path.getsize(file_path)
        file_duration = get_video_duration(file_path)
        
        # 检查是否超出限制
        would_exceed_duration = max_duration > 0 and (current_duration + file_duration) > max_duration
        would_exceed_size = max_size > 0 and (current_size + file_size) > max_size
        
        # 如果当前组不为空且添加当前文件会超出限制，则先合并当前组
        if current_group and (would_exceed_duration or would_exceed_size):
            # 合并当前组
            episode_str = f"{episode_num:02d}"
            success, result = merge_videos_ffmpeg(
                current_group, output_dir, show_name, season, episode_str
            )
            results.append((success, result))
            
            # 重置当前组和计数器
            current_group = []
            current_duration = 0
            current_size = 0
            episode_num += 1
        
        # 将当前文件添加到组中
        current_group.append(file_path)
        current_duration += file_duration
        current_size += file_size
    
    # 合并最后一组（如果有）
    if current_group:
        episode_str = f"{episode_num:02d}"
        success, result = merge_videos_ffmpeg(
            current_group, output_dir, show_name, season, episode_str
        )
        results.append((success, result))
    
    return results

def get_show_name_from_dir(source_dir: str) -> str:
    """
    根据输入的目录名，提取中文剧名
    """
    origin_name = os.path.basename(source_dir)

    m = re.search(r'《(.*?)》', origin_name) # 如果包含《》则提取其中内容作为correct_name
    if m:
        return m.group(1)

    name = re.sub(r'\d+', ' ', origin_name) # 将所有数字都转换成空格
    name = name.replace('-', ' ') # 将'-'转为空格
    name = name.replace('.', ' ') # 将'.'转为空格

    name = re.sub(r'（.*?）', ' ', name) # 将'（'和'）'里的字符以及括号都转换成空格
    name = re.sub(r'\(.*?\)', ' ', name)

    name = re.sub(r'\[.*?\]', ' ', name) # 将'['和']'里的字符以及括号都转换成空格
    name = re.sub(r'【.*?】', ' ', name)

    name = name.replace('《', ' ').replace('》', ' ') # 将'《'和'》'转换成空格

    # 按空格分割字符串，并标记每一段的顺序
    parts = [p for p in name.strip().split() if p]
    marked = []
    for idx, part in enumerate(parts):
        marked.append((part, idx))

    # 取第一段字符串作为show_name
    if parts:
        show_name = parts[0]
    else:
        show_name = ""

    logging.info(f"根据目录名（{origin_name}）提取到剧名: {show_name}")
    return show_name

def search_show_in_tmdb(show_name: str, tmdb_key: str, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    在TMDB中搜索给定的show_name，返回最匹配的结果
    """
    # 配置TMDB API密钥
    tmdb.API_KEY = tmdb_key
    
    # 配置代理（如果提供）
    if proxy_url:
        tmdb.REQUESTS_SESSION = tmdb.requests.Session()
        tmdb.REQUESTS_SESSION.proxies = {'http': proxy_url, 'https': proxy_url}
    
    try:
        # 创建搜索对象
        search = tmdb.Search()
        
        # 执行搜索
        response = search.tv(query=show_name, language='zh-CN')
        logging.debug(f"TMDB搜索响应: {response}")
        
        # 如果有结果，返回第一个（最匹配的）
        if search.results:
            logging.info(f"在 TMDB 搜索剧名（{show_name}），找到最佳匹配项: 剧名：《{search.results[0]['name']}》")
            return search.results[0]
        else:
            return None
    except Exception as e:
        logging.error(f"TMDB搜索错误: {e}")
        return None

def get_credits_from_tmdb(show_id: int, season_number: int, tmdb_key: str, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    从TMDB获取给定show_id的演职员表
    """
    # 配置TMDB API密钥
    tmdb.API_KEY = tmdb_key
    
    # 配置代理（如果提供）
    if proxy_url:
        tmdb.REQUESTS_SESSION = tmdb.requests.Session()
        tmdb.REQUESTS_SESSION.proxies = {'http': proxy_url, 'https': proxy_url}
    
    try:
        # 创建电视对象
        tv_seasons = tmdb.TV_Seasons(show_id, season_number)
        
        # 获取演职员表
        credits = tv_seasons.credits(language='zh-CN')
        logging.info(f"获取 {show_id} {season_number} 的演员列表")
        logging.debug(f"TMDB演职员表: {credits}")
        return credits
    except Exception as e:
        logging.error(f"TMDB获取演职员表错误: {e}")
        return None

def get_show_details_from_tmdb(show_id: int, tmdb_key: str, proxy_url: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    从TMDB获取给定show_id的电视剧详细信息，包括每季的详细信息
    """
    # 配置TMDB API密钥
    tmdb.API_KEY = tmdb_key
    
    # 配置代理（如果提供）
    if proxy_url:
        tmdb.REQUESTS_SESSION = tmdb.requests.Session()
        tmdb.REQUESTS_SESSION.proxies = {'http': proxy_url, 'https': proxy_url}
    
    try:
        # 创建电视对象
        tv = tmdb.TV(show_id)
        
        # 获取详细信息
        details = tv.info(language='zh-CN')
        logging.debug(f"TMDB电视剧详细信息: {details}")
        return details
    except Exception as e:
        logging.error(f"TMDB获取电视剧详细信息错误: {e}")
        return None

def format_table_data_show_details(details: Dict[str, Any], tmdb_key: str, proxy_url: Optional[str] = None) -> List[List[Any]]:
    """
    格式化TMDB电视剧详细信息
    """
    if not details:
        return []

    table_data = []
    show_id = details.get('id', 0)
    show_name = details.get('name', '未知')
    number_of_seasons = details.get('number_of_seasons', 0)
    number_of_episodes = details.get('number_of_episodes', 0)

    for season in details.get('seasons', []):
        season_number = season.get('season_number', 0)
        season_name = season.get('name', '未知')
        episode_count = season.get('episode_count', '未知')
        air_date = season.get('air_date', '未知')
        
        # 从TMDB获取演职员表
        season_credits = get_credits_from_tmdb(show_id, season_number, tmdb_key, proxy_url)
        if season_credits and isinstance(season_credits, dict):
            cast = season_credits.get('cast', [])
            top_5_actors = [actor.get('name', '未知') for actor in cast[:5]] if cast else ['未知']
            actors_str = '，'.join(top_5_actors)
        else:
            actors_str = '未知'

        table_data.append([span(f'S{season_number:02d}',row=2), style(put_text(season_name), 'font-weight: bold; width: 100px;'), f'{episode_count} 集', air_date, actors_str])

        overview = season.get('overview', '')
        if not overview:
            overview = details.get('overview', '未知')
        if not overview:
            overview = '未知'
        table_data.append([style(put_text('剧情'), 'font-weight: bold; width: 60px;'), span(overview, col=3)])
    
    return table_data