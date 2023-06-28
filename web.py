import re
import time
import sys
import json
import random
import hashlib
import logging
import traceback
from functools import wraps
from operator import itemgetter
from datetime import date, datetime

from flask import Flask, render_template, request, redirect, abort, session
from flask_sqlalchemy import SQLAlchemy
from tornado.httpserver import HTTPServer
from tornado.wsgi import WSGIContainer
from tornado.ioloop import IOLoop
from flask_cors import CORS
from bs4.element import Tag
import requests
import aiml
import bs4

app = Flask(__name__)
app.config['SECRET_KEY'] = 'khfbyu4tgbukys'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///qncblog.db'
CORS(app, supports_credential=True, resources={"/*", "*"})

db = SQLAlchemy(app)
app.app_context().push()

logger = logging.getLogger()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s-%(name)s:%(message)s'
)

time.clock = time.perf_counter
kernel = aiml.Kernel()
kernel.verbose(False)
kernel.loadBrain('aiml_brain')

def execute_sql(sql: str, **kwargs):
    return db.session.execute(sql, kwargs or None)

for user, aisession in execute_sql('SELECT user, session FROM ai'):
    kernel._sessions[user] = json.loads(aisession)
    kernel._sessions[user]['_inputStack'] = []
    for field, flag in (('_inputHistory', 1), ('_outputHistory', 0)):
        kernel._sessions[user][field] = list(map(
            itemgetter(0), 
            execute_sql('SELECT content FROM aichat WHERE user = :user AND human = :human', user=user, human=flag)
        ))

with open('words.txt', encoding='utf-8') as file:
    words = list(map(str.strip, file))

assets = {
    'today': date.today(),
    'hitokoto': {},
    'the_wors': '',
    'news': {},
    'wallpapers': [],
    'music': None
}
settings = {
    'muyu': True,
    'sound': True,
    'speed': 333,
    'offline': False,
    'music': False
}

def save_assets():
    tmp = assets.copy()
    tmp['today'] = tmp['today'].isoformat()
    with open('assets.json', 'w', encoding='utf-8') as file:
        json.dump(tmp, file, ensure_ascii=False)

def get_hitokoto():
    try:
        res = requests.get('https://v1.hitokoto.cn', timeout=5)
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout):
        ...
    else:
        if res.status_code == 200:
            assets['hitokoto'] = json.loads(res.text)
            return
    assets['hitokoto'] = {
        'hitokoto': 'https://v1.hitokoto.cn坏掉了',
        'from_who': '系统',
        'from': '错误信息'
    }
    save_assets()

def update(clear_muyu=True):
    assets['today'] = date.today()
    
    text = requests.get('https://cctv.cn').content.decode()
    soup = bs4.BeautifulSoup(text, 'lxml')
    assets['news'] = dict(
        focus=list(map(Tag.get_text, soup.find('div', {'class': 'boxTitle'}).find_all('div', class_='title'))),
        **{categ: list(map(Tag.get_text, content.find_all('li')))
            for categ, content in zip(['social', 'global'], soup.find_all('div', {'class': 'col_w380_r'}))},
        channels=list(map(Tag.get_text, soup.find('div', {'class': 'col_w400'}).find_all('p', {'class': 'text'})))
    )
    
    res = requests.get('https://bing.com/HPImageArchive.aspx?format=js&idx=0&n=7')
    assets['wallpapers'] = []
    for i, img in enumerate(json.loads(res.text)['images']):
        assets['wallpapers'].append((i, {
            'url': 'https://bing.com' + img['url'],
            'title': img['title'],
            'copyright': img['copyright']
        }))

    assets['the_word'] = random.choice(words)
    get_hitokoto()

    save_assets()
    logger.info('Updated')
    
    if not clear_muyu:
        return
    execute_sql('DELETE FROM muyu')
    db.session.commit()
    logger.info('Muyu cleared')

def comp(tag, name, *cls):
    for i in cls:
        ret = tag.find(name, {'class': i})
        if ret is None:
            yield ''
        else:
            yield ret.string
            
def get_weather():
    res = requests.get('https://www.msn.cn/zh-cn/weather/forecast/')
    match = re.search(r'\<script id="redux-data" type="application/json"\>([\s\S]+?)\</script\>', res.text)
    return json.loads(match.group(1))

def query_word(word: str, verbose: bool):
    if verbose:
        res = execute_sql('SELECT v FROM dict WHERE k = :k', k=word).fetchone()
        if res is not None:
            return json.loads(res[0])
        soup = bs4.BeautifulSoup(requests.get('https://cn.bing.com/dict?q=' + word).text, 'lxml')
        uls = list(soup.find_all('ul'))
        if len(uls) < 3:
            return {}
        pron = soup.find('div', {'class': 'hd_p1_1'})
        ret = {
            'explainations': list(map(Tag.get_text, uls[2].find_all('li'))),
            'pron': '' if pron is None else pron.get_text(),
            'sens': [],
            'more': []
        }
        main = soup.find('div', {'id': 'pos_0'})
        if main is not None:
            for head, body in zip(
                map(Tag.get_text, main.find_all('div', {'class': 'dis'})),
                main.find_all('div', {'class': 'li_exs'})
            ):
                ret['sens'].append((head, ['{} {}'.format(*comp(stc, 'div', 'bil_ex', 'val_ex'))
                                           for stc in body.find_all('div', {'class': 'li_ex'})]))
        execute_sql('INSERT INTO dict(k, v) VALUES(:k, :v)', k=word, v=json.dumps(ret, ensure_ascii=False))
        db.session.commit()
        return ret
    soup = bs4.BeautifulSoup(requests.get('https://cn.bing.com/dict/SerpHoverTrans?q=' + word).text, 'lxml')
    return {'explainations': map(Tag.get_text, soup.find_all('li'))}

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if 'id' not in session:
            return render_template('error.html', msg='未登录')
        return fn(*args, **kwargs, id=int(session.get('id')))
    return wrapper

def view(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if request.remote_addr == '172.31.33.251':
            abort(500)
        if date.today() != assets['today']:
            update()
        try:
            ret = fn(*args, **kwargs)
            db.session.commit()
            return ret
        except Exception as ex:
            db.session.rollback()
            traceback.print_exc()
            return render_template('error.html', msg='服务器遇到了{}'.format(ex.__class__.__qualname__))
    return wrapper

@app.route('/', methods=['GET', 'POST'])
@view
def index():
    if request.method == 'GET':
        args = dict.fromkeys(('times', 'issues', 'notices'))
        id = session.get('id')
        if id is not None:
            args['times'] = execute_sql(
                'SELECT COUNT(*) FROM issue WHERE author = :id AND time > :today', 
                id=id, 
                today=assets['today']
            ).fetchone()[0]
            args['issues'] = map(itemgetter(0), execute_sql(
                'SELECT content FROM issue WHERE author = :id ORDER BY ID DESC',
                id=id
            ))
        args['notices'] = map(itemgetter(0), execute_sql(
            'SELECT html FROM notice WHERE target IS NULL OR target = :id ORDER BY ID DESC',
            id=id
        ))
        return render_template(
            'index.html',
            id=id,
            name=session.get('name'),
            admin=session.get('id') == '20220905',
            **args
        )
    id, pwd = map(request.form.get, ('id', 'pwd'))
    if None in (id, pwd) or not id.isnumeric():
        return render_template('error.html', msg='表单校验错误')
    md5 = hashlib.md5()
    md5.update(pwd.encode())
    res = execute_sql('SELECT name FROM user WHERE id = :id AND pwd = :pwd', id=id, pwd=md5.hexdigest()).fetchone()
    if res is None:
        return render_template('error.html', msg='用户名或密码错误')
    session.update({
        'id': id,
        'name': res[0]
    })
    return redirect('/')

@app.route('/favicon.ico')
def icon():
    return redirect('/static/favicon.ico')

@app.route('/issue', methods=['POST'])
@login_required
@view
def issues(id: int):
    times = execute_sql('SELECT COUNT(*) FROM issue WHERE author = :id AND time > :today',
        id=id,
        today=assets['today']
    ).fetchone()[0]
    if times >= 5:
        return render_template('error.html', msg='反馈已达上限')
    content = request.form.get('content')
    if not content or content.isspace() or len(content) > 64:
        return render_template('error.html', msg='表单校验错误')
    execute_sql('INSERT INTO issue(author, content, time) VALUES(:author, :content, :time)',
        author=id, 
        content=content,
        time=datetime.now()
    )
    return render_template('success.html', msg='反馈成功')

@app.route('/mod-pwd', methods=['POST'])
@view
def mod_pwd():
    if request.method == 'GET':
        return render_template('modpwd.html', target=session.get('id'))
    target, old, new = map(request.form.get, ('target', 'old', 'new'))
    if session.get('id') != '20220905' and None in (target, old, new):
        return render_template('error.html', msg='表单校验错误')
    if target != session.get('id') and session.get('id') != '20220905':
        return render_template('error.html', msg='FUCK YOU')
    if session.get('id') != '20220905':
        md5 = hashlib.md5()
        md5.update(old.encode())
        res = execute_sql('SELECT * FROM user WHERE id = :id AND pwd = :pwd', id=target, pwd=md5.hexdigest()).fetchone()
        if res is None:
            return render_template('error.html', msg='旧密码错误')
    md5 = hashlib.md5()
    md5.update(new.encode())
    execute_sql('UPDATE user SET pwd = :pwd WHERE id = :id', id=target, pwd=md5.hexdigest())
    return render_template('success.html', msg='修改密码成功, 现在的密码是' + new)

@app.route('/logout')
@view
def logout():
    session.pop('id')
    session.pop('name')
    return redirect('/')

@app.route('/query')
@view
def query():
    word = request.args.get('word')
    if word is None:
        return render_template(
            'query.html',
            maxlength=20,
            prompt='单词'
        )
    word = word.strip().lower()
    if len(word) > 20:
        return render_template('error.html', msg='查询过长')
    if not word:
        return render_template('error.html', msg='查询过短')
    args = query_word(word, request.args.get('verbose'))
    return render_template(
        'result.html',
        word=word,
        **args
    )

@app.route('/more')
@view
def more():
    word, offset = map(request.args.get, ('word', 'offset'))
    if None in (word, offset):
        return render_template('error.html', msg='缺乏参数')
    try:
        offset = int(offset)
    except (ValueError, TypeError):
        return render_template('error.html', msg='参数类型错误')
    res = execute_sql('SELECT data FROM sen WHERE word = :word AND offset = :offset', word=word, offset=offset).fetchone()
    if res is not None:
        return render_template('more.html', **json.loads(res[0]), word=word, offset=offset)
    res = requests.get('https://cn.bing.com/dict/service?q={}&offset={}&dtype=sen&&qs=n'.format(word, offset * 10 - 10))
    soup = bs4.BeautifulSoup(res.text, 'lxml')
    pages = soup.find('div', {'class': 'b_pag'})
    if pages is None:
        return render_template('error.html', msg='无相关结果')
    pages = list(map(Tag.get_text, soup.find('div', {'class': 'b_pag'}).find_all('a', {'class': 'b_primtxt'})))
    more = list(map(Tag.get_text, soup.find_all('div', {'class': 'se_li'})))
    execute_sql('INSERT INTO sen(word, offset, data) VALUES(:word, :offset, :data)',
        word=word, 
        offset=offset, 
        data=json.dumps({'pages': pages, 'more': more})
    )
    return render_template('more.html', more=more, pages=pages, word=word, offset=offset)

@app.route('/wenyan')
@view
def wenyan():
    word = request.args.get('word')
    if word is None:
        return render_template(
            'query.html',
            maxlength=10,
            prompt='字词'
        )
    word = word.strip().lower()
    if len(word) > 10:
        return render_template('error.html', msg='查询过长')
    if not word:
        return render_template('error.html', msg='查询过短')
    res = execute_sql('SELECT v FROM wenyan WHERE k = :k', k=word).fetchone()
    if res:
        return render_template(
            **json.loads(res[0])
        )
    res = requests.get('https://www.zdic.net/hans/' + word)
    if not res.text:
        return render_template('error.html', msg='查无此结果')
    soup = bs4.BeautifulSoup(res.text, 'lxml')
    if res.url.startswith('https://www.zdic.net/e/sci/index.php'):
        if soup.find('li') is None:
            return render_template('error.html', msg='未找到结果')
        items = [i.get_text().rstrip(i.find('span').string) for i in soup.find('div', {'class': 'sslist'}).find_all('a')]
        data = {
            'template_name_or_list': 'wenyan_search.html',
            'count': len(items),
            'items': items
        }
    elif len(word) == 1:
        swjz = soup.find('div', {'class': 'swjz'})
        def maybe(cls: str, tagname: str):
            tag = soup.find('div', {'class': cls})
            if tag is None:
                return []
            return list(map(Tag.get_text, tag.find_all(tagname)))
        data = {
            'template_name_or_list': 'wenyan.html',
            'data': {
                '基本解释': maybe('jbjs', 'li'),
                '详细解释': maybe('xxjs', 'p'),
                '康熙字典': maybe('kxzd', 'p'),
                '说文解字': [swjz.find('p').get_text() if swjz is not None else '']
            }
        }
    else:
        data = {
            'template_name_or_list': 'wenyan.html',
            'data': {}
        }
        for head, cls in (('词语解释', 'jbjs'), ('网络解释', 'wljs')):
            tag = soup.find('div', {'class': cls})
            data['data'][head] = [] if tag is None else list(map(Tag.get_text, tag.find_all('li')))
    execute_sql('INSERT INTO wenyan(k, v) VALUES(:k, :v)', k=word, v=json.dumps(data, ensure_ascii=False))
    return render_template(
        **data
    )

@app.route('/hitokoto')
@view
def hitokoto():
    return render_template('hitokoto.html', **assets['hitokoto'])

@app.route('/word')
@view
def word_sharing():
    return redirect('/query?verbose=yes&word=' + assets['the_word'])

@app.route('/news')
@view
def news():
    return render_template('news.html', **assets['news'])

@app.route('/birthday', methods=['GET', 'POST'])
@view
def birthday():
    if request.method == 'GET':
        today = assets['today']
        args = {}
        args['today'] = map(itemgetter(0), execute_sql(
            'SELECT name '
            'FROM user '
            'WHERE id IN '
            '(SELECT id '
            'FROM birthday '
            'WHERE month = :month AND day = :day)',
            month=today.month, 
            day=today.day
        ))
        args['thismonth'] = execute_sql(
            'SELECT u.name, b.day '
            'FROM birthday AS b '
            'JOIN user AS u '
            'ON b.id = u.id '
            'WHERE b.month = :month '
            'ORDER BY b.day',
            month=today.month
        )
        args['month'] = today.month
        args['count'] = execute_sql('SELECT COUNT(*) FROM birthday').fetchone()[0]
        args['login'] = 'id' in session
        args['profile'] = None
        if args['login']:
            res = execute_sql('SELECT year, month, day FROM birthday WHERE id = :id', id=session.get('id')).fetchone()
            if res is not None:
                args['profile'] = (session.get('name'),) + tuple(res)
        return render_template('birthday.html', **args)
    if 'id' not in session:
        return render_template('error.html', msg='未登录')
    try:
        birthday = date.fromisoformat(request.form.get('birthday'))
    except (ValueError, TypeError):
        return render_template('error.html', msg='错误的日期格式')
    if execute_sql('SELECT * FROM birthday WHERE id = :id', id=session.get('id')).fetchone() is not None:
        return render_template('error.html', msg='生日已注册')
    execute_sql('INSERT INTO birthday(id, year, month, day) VALUES(:id, :year, :month, :day)', 
        id=session.get('id'), 
        year=birthday.year, 
        month=birthday.month, 
        day=birthday.day
    )
    return redirect('/birthday')

@app.route('/wallpapers')
@view
def bing_wallpapers():
    return render_template(
        'wallpaper.html', 
        imgs=assets['wallpapers']
    )

@app.route('/weather')
@view
def msn_weather():
    weather = get_weather()
    return render_template(
        'weather.html',
        **weather['WeatherData']['_@STATE@_'],
        datetime=datetime,
        zip=zip,
        location=weather['WeatherPageMeta']['_@STATE@_']['location']['displayName']
    )

@app.route('/3500')
@view
def words_3500():
    return render_template('3500.html')

@app.route('/muyu', methods=['GET', 'POST'])
@view
def muyu():
    if not settings['muyu']:
        return render_template('error.html', msg='都什么年代了还在抽传统反馈')
    id = session.get('id')
    if request.method == 'GET':
        res = execute_sql('SELECT count FROM muyu WHERE id = :id', id=id).fetchone()
        return render_template(
            'muyu.html', 
            count=0 if res is None else res[0],
            sound=settings['sound'],
            autospeed=settings['speed'],
            offline=('false', 'true')[settings['offline']]
        )
    count = request.form.get('count')
    if count is None or not count.isnumeric():
        return render_template('error.html', msg='表单校验错误')
    if count == '0':
        return redirect('/muyu')
    res = execute_sql('SELECT count FROM muyu WHERE id = :id', id=id).fetchone()
    if res is None:
        execute_sql('INSERT INTO muyu(id, count, anonymous) VALUES(:id, :count, 0)', id=id, count=count)
    else:
        execute_sql('UPDATE muyu SET count = count + :count WHERE id = :id', id=id, count=count)
    return redirect('/muyu')

@app.route('/muyu-ranking', methods=['GET', 'POST'])
@view
def muyu_ranking():
    if not settings['muyu']:
        return render_template('error.html', msg='都什么年代了还在抽传统反馈')
    id = session.get('id')
    if request.method == 'POST':
        anonymous = request.form.get('anonymous')
        if anonymous is None or not anonymous.isnumeric():
            return render_template('error.html', msg='表单校验错误')
        if id is None:
            return render_template('error.html', msg='未登录')
        execute_sql('UPDATE MUYU SET anonymous = :anonymous WHERE id = :id', id=id, anonymous=anonymous)
        return redirect('/muyu')
    login = id is not None
    anonymous = False
    if login:
        res = execute_sql('SELECT anonymous FROM muyu WHERE id = :id', id=id).fetchone()
        if res is None:
            login = False
        else:
            anonymous = res[0]
    data = execute_sql(
        'SELECT u.name, m.id, m.count '
        'FROM muyu AS m '
        'JOIN user AS u '
        'ON u.id = m.id '
        'WHERE anonymous = 0 '
        'ORDER BY m.count DESC'
    ).fetchall()
    return render_template(
        'ranking.html', 
        data=enumerate(data),
        login=login,
        anonymous=anonymous
    )

@app.route('/heartbeat')
def muyu_enabled():
    return json.dumps({
        'muyu': settings['muyu'],
        'music': settings['music']
    })

@app.route('/edit-notices', methods=['GET', 'POST'])
@view
def edit_notices():
    if session.get('id') != '20220905':
        return render_template('error.html', msg='FUCK YOU')
    if request.method == 'GET':
        data = execute_sql(
            'SELECT u.name, n.id, n.target, n.html '
            'FROM notice AS n '
            'LEFT JOIN user AS u '
            'ON n.target = u.id '
            'ORDER BY n.id DESC'
        ).fetchall()
        return render_template('editnotices.html', data=data)
    if request.form.get('delete'):
        execute_sql('DELETE FROM notice WHERE id = :id', id=request.form.get('id'))
    else:
        execute_sql(
            'UPDATE notice SET html = :html WHERE id = :id', 
            id=request.form.get('id'), 
            html=request.form.get('html')
        )
    return redirect('/edit-notices')

@app.route('/ai', methods=['GET', 'POST'])
@login_required
@view
def ai(id: int):
    count = execute_sql(
        'SELECT COUNT(*) FROM aichat WHERE user = :id AND time > :today', 
        id=id, 
        today=assets['today']
    ).fetchone()[0]
    if request.method == 'GET':
        res = execute_sql('SELECT human, content FROM aichat WHERE user = :id ORDER BY time', id=id).fetchall()
        return render_template('ai.html', session=res, count=count, name=session.get('name'))
    if count >= 40:
        return render_template('error.html', msg='使用次数过多')
    text = request.form.get('text')
    if not text or len(text) > 256:
        return render_template('error.html', msg='表单校验错误')
    if re.search(r'\bsing\b', text, re.I):
        return render_template('error.html', msg='你这小子, 想让AIML唱歌是罢')
    now = datetime.now()
    response = kernel.respond(text, id)
    if not response:
        return render_template('error.html', msg='AIML没有响应')
    for content, human in ((text, 1), (response, 0)):
        execute_sql(
            'INSERT INTO aichat(user, human, content, time) VALUES(:user, :human, :content, :time)',
            user=id,
            content=content,
            human=human,
            time=now
        )
    aisession = json.dumps({k: v for k, v in kernel._sessions[id].items() if k[0] != '_'}, ensure_ascii=False)
    if execute_sql('SELECT COUNT(*) FROM ai WHERE user = :id', id=id).fetchone()[0] == 0:
        execute_sql('INSERT INTO ai(user, session) VALUES(:user, :session)', user=id, session=aisession)
    else:
        execute_sql('UPDATE ai SET session = :session WHERE user = :user', user=id, session=aisession)
    return redirect('/ai')

@app.route('/music-search', methods=['GET', 'POST'])
@view
def music_search():
    if session.get('id') != '20220905':
        return render_template('error.html', msg='FUCK YOU')
    if request.method == 'GET':
        data = json.loads(requests.get(
            'https://music-api.tonzhon.com/search?keyword={}&platform=qq&limit=25'.format(request.args.get('keyword'))
        ).text)['data']['songs']
        for datum in data:
            datum['url'] = json.loads(requests.get('https://music-api.tonzhon.com/song_file/' + datum['newId']).text)['data']['songSource']
        return render_template('music_search.html', data=data)
    assets['music'] = dict(request.form)
    save_assets()
    return render_template('success.html', msg='音乐已设置为{}'.format(assets['music']['title']))

@app.route('/music-admin', methods=['GET', 'POST'])
@view
def music_admin():
    if session.get('id') != '20220905':
        return render_template('error.html', msg='FUCK YOU')
    if request.method == 'GET':
        return render_template('music_admin.html', music=settings['music'])
    save_settings(music=bool(int(request.form.get('music'))))
    return render_template('success.html', msg='音乐已{}'.format('打开' if settings['music'] else '关闭'))

@app.route('/music')
@view
def radio_station():
    if not settings['music']:
        return render_template('error.html', msg='广播站已关闭')
    if not assets['music']:
        return render_template('error.html', msg='今天没有音乐')
    return render_template('music.html', **assets['music'])

@app.route('/admin', methods=['GET', 'POST'])
@view
def admin():
    if session.get('id') != '20220905':
        return render_template('error.html', msg='FUCK YOU')
    if request.method == 'GET':
        issues = execute_sql(
            'SELECT u.name, i.author, i.content '
            'FROM issue AS i '
            'JOIN user AS u '
            'ON i.author = u.id '
            'ORDER BY i.id DESC'
        ).fetchall()
        return render_template('admin.html', issues=issues, settings=settings)
    match request.form:
        case {'task': 'set-muyu'}:
            save_settings(muyu=not settings['muyu'])
            return render_template('success.html', msg='木鱼设置为{}'.format(settings['muyu']))
        case {'task': 'set-sound'}:
            save_settings(sound=not settings['sound'])
            return render_template('success.html', msg='木鱼声音{}'.format(settings['sound']))
        case {'task': 'next-saying'}: 
            get_hitokoto()
            return redirect('/hitokoto')
        case {'task': 'edit-saying', **rest}:
            assets['hitokoto'] = rest
            save_assets()
            return redirect('/hitokoto')
        case {'task': 'send-notice', 'target': target, 'html': html}:
            execute_sql(
                'INSERT INTO notice(target, html) VALUES(:target, :html)', 
                target=target or None, 
                html=html
            )
            return render_template('success.html', msg='通知发送给了{}'.format(target))
        case {'task': 'mod-birthday', 'birthday': birthday, 'target': target}:
            birthday = date.fromisoformat(birthday)
            args = {
                'id': target,
                'year': birthday.year,
                'month': birthday.month,
                'day': birthday.day
            }
            if execute_sql('SELECT * FROM birthday WHERE id = :id', id=target).fetchone() is None:
                execute_sql(
                    'INSERT INTO birthday(id, year, month, day) '
                    'VALUES(:id, :year, :month, :day)',
                    **args
                )
            else:
                execute_sql(
                    'UPDATE birthday '
                    'SET year = :year, month = :month, day = :day '
                    'WHERE id = :id',
                    **args
                )
            return render_template('success.html', msg='修改了' + target)
        case {'task': 'del-birthday', 'target': target}:
            execute_sql('DELETE FROM birthday WHERE id = :id', id=target)
            return render_template('success.html', msg='删除了{}'.format(target))
        case {'task': 'query-id', 'id': id}:
            res = execute_sql('SELECT name FROM user WHERE id = :id', id=id).fetchone()
            if res is None:
                return render_template('error.html', msg='未查询到' + id)
            return render_template('success.html', msg=res[0])
        case {'task': 'query-name', 'name': name}:
            msg = execute_sql('SELECT id, name FROM user WHERE name LIKE :name', name='%' + name + '%').fetchall()
            return render_template('success.html', msg=str(msg))
        case {'task': 'login', 'id': id}:
            session.update({
                'id': id,
                'name': execute_sql('SELECT name FROM user WHERE id = :id', id=id).fetchone()[0]
            })
            return redirect('/')
        case {'task': 'set-count', 'id': id, 'count': count}:
            if count == '0':
                execute_sql('DELETE FROM muyu WHERE id = :id', id=id)
            else:
                res = execute_sql('SELECT COUNT(*) FROM muyu WHERE id = :id', id=id).fetchone()[0]
                if res > 0:
                    execute_sql('UPDATE muyu SET count = :count WHERE id = :id', id=id, count=count)
                else:
                    execute_sql('INSERT INTO muyu(id, count) VALUES(:id, :count)', id=id, count=count)
            return render_template('success.html', msg='将{}的木鱼设置为{}'.format(id, count))
        case {'task': 'muyu-speed', 'speed': speed}:
            save_settings(speed=speed)
            return render_template('success.html', msg='将木鱼速度设置为{}'.format(speed))
        case {'task': 'set-offline'}:
            save_settings(offline=not settings['offline'])
            return render_template('success.html', msg='木鱼{}允许离线运行'.format('' if settings['offline'] else '不'))
        case {'task': 'clear-issues'}:
            execute_sql('DELETE FROM issue')
            return render_template('success.html', msg='清除成功')
        case _:
            return render_template('error.html', msg='无效参数: ' + str(request.form))
        
def save_settings(**updates):
    settings.update(updates)
    with open('settings.json', 'w', encoding='utf-8') as file:
        json.dump(settings, file)

if __name__ == '__main__':
    try:
        file = open('assets.json', encoding='utf-8')
    except OSError:
        update(False)
    else:
        assets = json.load(file)
        assets['today'] = date.fromisoformat(assets['today'])
        file.close()
    try:
        file = open('settings.json', encoding='utf-8')
    except OSError:
        ...
    else:
        settings = json.load(file)
        file.close()
    if len(sys.argv) == 1:
        port = 19198
    else:
        port = int(sys.argv[1])
    wsgi = WSGIContainer(app)
    server = HTTPServer(wsgi)
    server.listen(port)
    logger.info('Server started')
    IOLoop.instance().start()