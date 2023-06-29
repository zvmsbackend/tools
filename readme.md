# 蚯鲇蜍的工具箱

## 部署

1. 将仓库clone到本地
```sh
$ git clone https://github.com/zvmsbackend/tools.git
```
2. 安装python依赖项
```sh
$ pip3 -r requirements.txt
```
3. 初始化数据库(假设使用litecli)
```sh
$ mkdir instance
$ litecli instance/qncblog.db
```
```sql
source sql.sql
```
或者使用python的sqlite3模块:
```python
import sqlite3
connection = sqlite3.connect('instance/qncblog.db')
cursor = connection.cursor()
with open('sql.sql', encoding='utf-8') as file:
    script = file.read()
cursor.execute_script(script)
connection.commit()
connection.close()
```
4. 创建管理员账号(必须为20220905)
```sql
INSERT INTO user(id, name) VALUES(20220905, "你的名字")
```
5. 运行服务
```sh
$ python web.py
```
或者指定端口:
```sh
$ python web.py <port>
```