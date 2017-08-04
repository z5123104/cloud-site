"""
CREAT: 2017/5/6
AUTHOR:　HEHAHUTU
"""
from datetime import datetime, timedelta
from flask.views import MethodView
from manage.models import *
from flask import jsonify, request, render_template, send_file, send_from_directory, session, redirect, url_for, \
    make_response
import os, shutil
from admin.login import check_login
import admin.models
from sqlalchemy import and_
import zipfile, time
from helper.creat_hash import creat_hash
import urllib.parse

"""
删除文件：
    针对文件会直接将其is_trash 设置为1,过期时间update_time 加30天，
同时可用空间会减去当前文件的大小；
    文件夹，现在为了减小前端工作量，在后台将所有属于该文件夹的文件夹
和文件is_trash 设置为1,过期时间update_time 加30天。

恢复文件：
    文件会直接恢复is_trash 设置为0,过期时间update_time 更新为当前时间
同时可用空间会减去当前文件的大小；
    文件夹，只会恢复该文件夹，不会恢复所属文件夹和文件。

"""


class IndexPage(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return redirect(url_for('admin.login'))
        if check_user == -1:
            return '抱歉您的账号过期，请联  系管理员'
        else:
            return render_template('manage/home.html')


class GetFiles(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            user_id = session.get('user_id')
            folder_path = request.args.get('diskPath', '/disk')
            is_trash = request.args.get('is_trash', 0)
            if folder_path == '':
                folder_path = '/disk'
            if is_trash == '':
                is_trash = 0
            folder_id = db.session.query(DiskFolder.id).filter(DiskFolder.folder_path == folder_path,
                                                               DiskFolder.user_id == user_id).scalar()

            folders_group = db.session.query(DiskFolder).filter(DiskFolder.group_id == folder_id,
                                                                DiskFolder.is_trash == is_trash,
                                                                DiskFolder.user_id == user_id).all()
            files_group = db.session.query(DiskFile).filter(DiskFile.folder_group_id == folder_id,
                                                            DiskFile.is_trash == is_trash,
                                                            DiskFile.user_id == user_id).all()
            folders = [folders.to_json() for folders in folders_group]
            files = [files.to_json() for files in files_group]

            return jsonify({'status': 'ok', 'path': folder_path.split('/')[1:], 'now_path': folder_path, 'file': files,
                            'folders': folders})

    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            user_id = session.get('user_id')
            folder_id = request.form.get('key')
            is_trash = request.args.get('is_trash', 0)
            if is_trash == '':
                is_trash = 0
            user = admin.models.db.session.query(admin.models.Users).filter(
                admin.models.Users.id == user_id).one_or_none()
            if user.authority in [0, 1]:
                folder = db.session.query(DiskFolder).filter(DiskFolder.id == folder_id,
                                                             DiskFolder.user_id == user_id).one_or_none()
                files_group = db.session.query(DiskFile).filter(DiskFile.folder_group_id == folder_id,
                                                                DiskFile.is_trash == is_trash,
                                                                DiskFile.user_id == user_id,
                                                                DiskFile.is_user_group == 1).all()

                files = [files.to_json() for files in files_group]

                return jsonify({'status': 'ok', 'path': folder.folder_name, 'file': files,
                                'folder_id': folder_id})
            else:
                folder = db.session.query(DiskFolder).filter(DiskFolder.id == folder_id,
                                                             DiskFolder.user_id == user.user_group_id).one_or_none()
                files_group = db.session.query(DiskFile).filter(DiskFile.folder_group_id == folder_id,
                                                                DiskFile.is_trash == is_trash,
                                                                DiskFile.user_id == user.user_group_id,
                                                                DiskFile.is_user_group == 1).all()

                files = [files.to_json() for files in files_group]

                return jsonify({'status': 'ok', 'path': folder.folder_name, 'file': files,
                                'folder_id': folder_id})


class GetUseSize(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            user_id = session.get('user_id')
            userlog = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
            all_size = admin.models.db.session.query(admin.models.Users.use_size).filter(
                admin.models.Users.id == user_id).scalar()
            if userlog:
                if userlog.use_disk_size > 1024:
                    size = str(userlog.use_disk_size / 1024).split('.')[0]
                    new_size = f'{size}'
                else:
                    size = str(userlog.use_disk_size).split('.')[0]
                    new_size = f'{size}K'
                return jsonify({'all': all_size, 'use': new_size})
            else:
                all_files = db.session.query(DiskFile).filter(DiskFile.user_id == user_id).all()

                use_size = 0
                for item in all_files:
                    use_size = use_size + int(item.file_size)

                use = UseLog(user_id, use_size)
                db.session.add(use)
                db.session.commit()
                return jsonify({'all': all_size, 'use': use_size})


class CreateFolder(MethodView):
    def post(self):

        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            user_id = session.get('user_id')
            check_authority = admin.models.db.session.query(admin.models.Users.is_create_folder).filter(
                admin.models.Users.id == user_id).scalar()
            if check_authority == 0:
                return jsonify({'status': 'error', 'msg': '抱歉您无此权限，请联系管理员'})
            else:
                path = request.form.get('path')
                folder = request.form.get('folder')
                if folder == '' and len(folder) > 20 and folder is None:
                    user = admin.models.db.session.query(admin.models.Users).filter(
                        admin.models.Users.id == user_id).one_or_none()
                    user.is_create_folder = 0
                    admin.models.db.session.commit()
                    return jsonify({'status': 'error', 'msg': '您涉嫌非法操作，已被系统关闭此权限！'})
                else:
                    new_path = path + '/' + folder
                    check_repeat = db.session.query(DiskFolder).filter(DiskFolder.folder_path == new_path,
                                                                       DiskFolder.user_id == user_id).one_or_none()
                    if check_repeat:
                        return jsonify({'status': 'error', 'msg': '该目录下已存在该文件，请换个名字'})
                    else:
                        group_id = db.session.query(DiskFolder.id).filter(DiskFolder.folder_path == path,
                                                                          DiskFolder.user_id == user_id).scalar()
                        create_time = datetime.now()

                        fol = DiskFolder(folder, new_path, group_id, user_id, 0, 0, 0, create_time, create_time)
                        db.session.add(fol)
                        db.session.commit()
                        return jsonify({'status': 'ok', 'msg': folder})


class UploadFiles(MethodView):
    def post(self):

        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        file_path = request.form.get('path')
        group_id = request.form.get('key', None)
        file = request.files.get('file_data')

        user_id = session.get('user_id')
        if group_id:
            user = admin.models.db.session.query(admin.models.Users).filter(
                admin.models.Users.id == user_id).one_or_none()
            if user:
                if 0 <= user.authority <= 1:
                    check_upload = admin.models.db.session.query(admin.models.Users.is_upload_folder).filter(
                        admin.models.Users.id == user_id).scalar()
                    if check_upload:
                        max_size = admin.models.db.session.query(admin.models.Users.use_size).filter(
                            admin.models.Users.id == user_id).scalar()
                        use_size = db.session.query(UseLog.use_disk_size).filter(UseLog.user_id == user_id).scalar()
                        if use_size is None:
                            user_log = UseLog(user_id)
                            db.session.add(user_log)
                            db.session.commit()
                        use_size = db.session.query(UseLog.use_disk_size).filter(UseLog.user_id == user_id).scalar()
                        if max_size > (use_size / 1024):
                            save_path = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                                admin.models.Users.id == user_id).scalar()
                            file_name = file.filename
                            check_file_name = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                                                DiskFile.file_name == file_name).one_or_none()
                            create_time = datetime.now()
                            if check_file_name:
                                save_file_name = os.path.splitext(file_name)[0] + create_time.strftime('%Y%H%M%f') + \
                                                 os.path.splitext(file_name)[1]
                            else:
                                save_file_name = file_name

                            save_path = 'static/disk' + save_path
                            group_folder_id = group_id
                            file.save(os.path.join(save_path, save_file_name))
                            file_size = os.path.getsize(os.path.join(save_path, save_file_name)) / 1024

                            # 更新使用容量
                            now_use_size = use_size + file_size
                            user_log = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                            user_log.use_disk_size = now_use_size
                            user_log.upload = file_name
                            user_log.time = datetime.now()
                            db.session.commit()

                            file_db = DiskFile(file_name, save_file_name, file_size, 'group', group_folder_id,
                                               user_id,
                                               creat_time=create_time, update_time=create_time, is_user_group=1)
                            db.session.add(file_db)
                            db.session.commit()

                            return jsonify({'status': 'ok', 'msg': '文件上传成功，请关闭此页面'})
                        else:
                            return jsonify({'status': 'error', 'msg': '抱歉您的空间已不足无法上传文件，请联系管理员'})

                    else:
                        return jsonify({'status': 'error', 'msg': '抱歉您无上传文件权限，请联系管理员'})
                else:
                    return jsonify({'status': 'error', 'msg': 'user is valid'})
            else:
                return jsonify({'status': 'error', 'msg': 'user is valid'})


        else:
            if '/dis' in file_path:
                check_upload = admin.models.db.session.query(admin.models.Users.is_upload_folder).filter(
                    admin.models.Users.id == user_id).scalar()
                if check_upload:
                    max_size = admin.models.db.session.query(admin.models.Users.use_size).filter(
                        admin.models.Users.id == user_id).scalar()
                    use_size = db.session.query(UseLog.use_disk_size).filter(UseLog.user_id == user_id).scalar()
                    if use_size is None:
                        user_log = UseLog(user_id)
                        db.session.add(user_log)
                        db.session.commit()
                    use_size = db.session.query(UseLog.use_disk_size).filter(UseLog.user_id == user_id).scalar()
                    if max_size > (use_size / 1024):
                        save_path = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                            admin.models.Users.id == user_id).scalar()
                        file_name = file.filename
                        check_file_name = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                                            DiskFile.file_name == file_name).one_or_none()
                        create_time = datetime.now()
                        if check_file_name:
                            save_file_name = os.path.splitext(file_name)[0] + create_time.strftime('%Y%H%M%f') + \
                                             os.path.splitext(file_name)[1]
                        else:
                            save_file_name = file_name

                        save_path = 'static/disk' + save_path
                        group_folder_id = db.session.query(DiskFolder.id).filter(DiskFolder.user_id == user_id,
                                                                                 DiskFolder.folder_path == file_path).scalar()
                        file.save(os.path.join(save_path, save_file_name))
                        file_size = os.path.getsize(os.path.join(save_path, save_file_name)) / 1024

                        # 更新使用容量
                        now_use_size = use_size + file_size
                        user_log = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                        user_log.use_disk_size = now_use_size
                        user_log.upload = file_name
                        user_log.time = datetime.now()
                        db.session.commit()

                        file_db = DiskFile(file_name, save_file_name, file_size, file_path, group_folder_id, user_id,
                                           creat_time=create_time, update_time=create_time, is_user_group=0)
                        db.session.add(file_db)
                        db.session.commit()

                        return jsonify({'status': 'ok', 'msg': '文件上传成功，请关闭此页面'})
                    else:
                        return jsonify({'status': 'error', 'msg': '抱歉您的空间已不足无法上传文件，请联系管理员'})

                else:
                    return jsonify({'status': 'error', 'msg': '抱歉您无上传文件权限，请联系管理员'})
            else:
                user = admin.models.db.session.query(admin.models.Users).filter(
                    admin.models.Users.id == user_id).one_or_none()
                user.is_upload_folder = 0
                admin.models.db.session.commit()
                return jsonify({'status': 'error', 'msg': '抱歉系统判定您涉嫌非法操作，已将您的上传权限关闭！'})


class Download(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        data_key = request.args.get('data')
        user_id = session.get('user_id')
        if 'file' in data_key or 'folder' in data_key:

            check_download = admin.models.db.session.query(admin.models.Users.is_download_folder).filter(
                admin.models.Users.id == user_id).scalar()
            if check_download == 1:
                if 'file' in data_key:
                    file_id = int(data_key.split('.')[-1])
                    filename = db.session.query(DiskFile.file_name).filter(DiskFile.id == file_id,
                                                                           DiskFile.is_trash == 0,
                                                                           DiskFile.user_id == user_id).scalar()
                    user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                        admin.models.Users.id == user_id).scalar()
                    file_path = f'{user_folder}/{filename}'
                    return jsonify({'status': 'ok', 'folder': user_folder, 'filename': filename, 'msg': '文件已下载成功'})
                elif 'folder' in data_key:
                    folder_id = int(data_key.split('.')[-1])
                    folder = db.session.query(DiskFolder).filter(DiskFolder.id == folder_id,
                                                                 DiskFolder.is_trash == 0,
                                                                 DiskFolder.user_id == user_id).one_or_none()
                    files = db.session.query(DiskFile.file_name).filter(and_(
                        DiskFile.file_path.like(f'{folder.folder_path}%'), DiskFolder.is_trash == 0,
                                                                           DiskFolder.user_id == user_id)).all()
                    user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                        admin.models.Users.id == user_id).scalar()
                    if files:

                        if os.path.exists('static/disk/zip_folder'):
                            shutil.rmtree('static/disk/zip_folder/')

                        os.mkdir('static/disk/zip_folder')

                        zip_folder = folder.folder_name
                        os.mkdir(f'static/disk/zip_folder/{zip_folder}/')
                        for name in files:
                            shutil.copy(f'static/disk/{user_folder}/{name[0]}',
                                        os.path.abspath(f'static/disk/zip_folder/{zip_folder}'))

                        folder_files = os.listdir(f'static/disk/zip_folder/{zip_folder}')

                        zip = zipfile.ZipFile('static/disk/zip_folder/{}.tar.zip'.format(zip_folder), 'w',
                                              zipfile.ZIP_DEFLATED)
                        zip.write(f'static/disk/zip_folder/{zip_folder}', zip_folder)
                        for file in folder_files:
                            zip.write(f'static/disk/zip_folder/{zip_folder}/{file}', f'{zip_folder}/{file}')
                        return jsonify(
                            {'status': 'ok', 'folder': '', 'filename': '{}.tar.zip'.format(zip_folder),
                             'msg': '文件已下载成功'})

                    else:
                        return jsonify({'status': 'error', 'msg': '抱歉该目录下无文件！'})



                else:
                    return jsonify({'status': 'error', 'msg': '抱歉获取数据错误，请联系管理员！'})
            else:
                return jsonify({'status': 'error', 'msg': '抱歉您无下载文件权限，请联系管理员！'})
        else:
            user = admin.models.db.session.query(admin.models.Users).filter(
                admin.models.Users.id == user_id).one_or_none()
            user.is_download_folder = 0
            admin.models.db.session.commit()
            return jsonify({'status': 'error', 'msg': '抱歉系统判定您涉嫌非法操作，已将您的下载权限关闭！'})


class ResponseFile(MethodView):
    def get(self):

        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        user_folder = request.args.get('key')
        filename = request.args.get('filename')
        if user_folder == '':
            path = f'static/disk/zip_folder/{filename}'

        else:
            path = f'static/disk/{user_folder}/{filename}'
        with open(path, 'rb') as f:
            data = f.read()
        resp = make_response(data)
        name = urllib.parse.quote(filename)

        resp.headers["Content-Disposition"] = f"attachment; filename*=utf-8''{name}"
        resp.headers["Content-Type"] = f"application/octet-stream; charset=utf-8"

        return resp


# 删除操作
class DeleteFile(MethodView):
    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        file = request.form.get('key')

        user_id = session.get('user_id')
        if ',' in file:
            da = file.split(',')
            for file in da:
                key = int(file.split('.')[-1])
                if 'folder' in file:
                    fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                              DiskFolder.id == key).one_or_none()
                    vail_date = datetime.now() + timedelta(days=30)
                    fol.update_time = vail_date
                    fol.is_trash = 1
                    db.session.commit()
                    group_fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                                    DiskFolder.group_id == fol.id).all()
                    if group_fol:
                        for item in group_fol:
                            vail_date = datetime.now() + timedelta(days=30)
                            item.update_time = vail_date
                            item.is_trash = 1
                            db.session.commit()
                    group_fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                                  DiskFile.folder_group_id == fol.id).all()
                    if group_fil:
                        for item in group_fil:
                            vail_date = datetime.now() + timedelta(days=30)
                            item.update_time = vail_date
                            item.is_trash = 1
                            db.session.commit()
                            use_size = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                            use_size.use_disk_size = use_size.use_disk_size - item.file_size
                            db.session.commit()

                elif 'file' in file:
                    fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                            DiskFile.id == key).one_or_none()
                    vail_date = datetime.now() + timedelta(days=30)
                    fil.update_time = vail_date
                    fil.is_trash = 1
                    db.session.commit()
                    use_size = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                    use_size.use_disk_size = use_size.use_disk_size - fil.file_size
                    db.session.commit()

                else:
                    return jsonify({'status': 'error', 'msg': 'ERROR'})
            return jsonify({'status': 'ok', 'msg': '文件删除成功，将保存在回收站1个月'})
        else:
            key = int(file.split('.')[-1])
            if 'folder' in file:
                fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                          DiskFolder.id == key).one_or_none()
                vail_date = datetime.now() + timedelta(days=30)
                fol.update_time = vail_date
                fol.is_trash = 1
                db.session.commit()
                group_fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                                DiskFolder.group_id == fol.id).all()
                if group_fol:
                    for item in group_fol:
                        vail_date = datetime.now() + timedelta(days=30)
                        item.update_time = vail_date
                        item.is_trash = 1
                        db.session.commit()
                group_fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                              DiskFile.folder_group_id == fol.id).all()
                if group_fil:
                    for item in group_fil:
                        vail_date = datetime.now() + timedelta(days=30)
                        item.update_time = vail_date
                        item.is_trash = 1
                        db.session.commit()
                        use_size = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                        use_size.use_disk_size = use_size.use_disk_size - item.file_size
                        db.session.commit()
                return jsonify({'status': 'ok', 'msg': '文件删除成功，将保存在回收站1个月'})
            elif 'file' in file:
                fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id, DiskFile.id == key).one_or_none()
                vail_date = datetime.now() + timedelta(days=30)
                fil.update_time = vail_date
                fil.is_trash = 1
                db.session.commit()
                use_size = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                use_size.use_disk_size = use_size.use_disk_size - fil.file_size
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': '文件删除成功，将保存在回收站1个月'})
            else:
                return jsonify({'status': 'error', 'msg': 'ERROR'})


# 生成分享链接
class CreateShareUlr(MethodView):
    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        file = request.form.get('key')
        user_id = session.get('user_id')
        if ',' in file:
            da = file.split(',')
            folder_list = []
            file_list = []

            for file in da:
                key = file.split('.')[-1]
                if 'folder' in file:
                    folder_list.append(key)

                elif 'file' in file:
                    file_list.append(key)

                else:
                    return jsonify({'status': 'error', 'msg': 'ERROR'})
            vail_date = datetime.now() + timedelta(days=90)
            share_key = creat_hash(str(time.time()))
            fo = ','.join(folder_list)
            fi = ','.join(file_list)
            share = ShareGroups(user_id, fo, fi, vail_date, share_key)
            db.session.add(share)
            db.session.commit()
            return jsonify({'status': 'ok', 'msg': share_key})
        else:

            if 'file' in file:

                file_id = file.split('.')[-1]
                vail_date = datetime.now() + timedelta(days=90)
                key = creat_hash(str(time.time()))
                share = ShareGroups(user_id, 0, file_id, vail_date, key)
                db.session.add(share)
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': key})
            elif 'folder' in file:
                folder_id = file.split('.')[-1]
                vail_date = datetime.now() + timedelta(days=90)
                key = creat_hash(str(time.time()))
                share = ShareGroups(user_id, folder_id, 0, vail_date, key)
                db.session.add(share)
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': key})
            else:
                return jsonify({'status': 'ok', 'msg': '抱歉服务器遇到无法克服的错误'})


# 分享页面
class Share(MethodView):
    def get(self, key):
        share_file = db.session.query(ShareGroups).filter(ShareGroups.share_key == key).one_or_none()
        reqfo = request.args.get('folderId')
        if reqfo:
            name = admin.models.db.session.query(admin.models.Users.show_name).filter(
                admin.models.Users.id == share_file.user_id).scalar()
            folder = db.session.query(DiskFolder).filter(DiskFolder.id == reqfo, DiskFolder.is_trash == 0).one_or_none()
            folder_group = db.session.query(DiskFolder).filter(DiskFolder.group_id == folder.id,
                                                               DiskFolder.is_trash == 0).all()
            file_group = db.session.query(DiskFile).filter(DiskFile.folder_group_id == folder.id,
                                                           DiskFile.is_trash == 0).all()
            foldernames = []
            filenames = []
            for fo in folder_group:
                foldernames.append(fo)
            for fi in file_group:
                filenames.append(fi)
            return render_template('manage/share.html', key=key, share_file=share_file, name=name, filenames=filenames,
                                   foldernames=foldernames)

        else:
            if share_file:
                name = admin.models.db.session.query(admin.models.Users.show_name).filter(
                    admin.models.Users.id == share_file.user_id).scalar()
                folder = share_file.folders
                file = share_file.files
                foldernames = []
                filenames = []
                for fo in folder.split(','):
                    foname = db.session.query(DiskFolder).filter(DiskFolder.id == fo,
                                                                 DiskFolder.is_trash == 0).one_or_none()
                    foldernames.append(foname)
                for fi in file.split(','):
                    finame = db.session.query(DiskFile).filter(DiskFile.id == fi, DiskFile.is_trash == 0).one_or_none()
                    filenames.append(finame)
                return render_template('manage/share.html', key=key, share_file=share_file, name=name,
                                       filenames=filenames,
                                       foldernames=foldernames)
            else:
                return '抱歉您请求的页面不存在'


# 分享链接，下载
class ShareDownload(MethodView):
    def get(self, key):
        fileid = request.args.get('fileId')
        user_id = db.session.query(ShareGroups.user_id).filter(ShareGroups.share_key == key).scalar()
        file = db.session.query(DiskFile).filter(DiskFile.user_id == user_id, DiskFile.id == fileid,
                                                 DiskFile.is_trash == 0).one_or_none()
        user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
            admin.models.Users.id == user_id).scalar()
        path = f'static/disk{user_folder}/{file.file_name}'
        with open(path, 'rb') as f:
            data = f.read()
        resp = make_response(data)
        name = urllib.parse.quote(file.show_name)

        resp.headers["Content-Disposition"] = f"attachment; filename*=utf-8''{name}"
        resp.headers["Content-Type"] = f"application/octet-stream; charset=utf-8"

        return resp


# 回收站
class Trash(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return redirect(url_for('admin.login'))
        if check_user == -1:
            return '抱歉您的账号过期，请联系管理员'
        return render_template('manage/trash.html')

    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        user_id = session.get('user_id')
        folder_path = request.args.get('diskPath', '/disk')

        folders_group = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                            DiskFolder.is_trash == 1).all()
        files_group = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                        DiskFile.is_trash == 1).all()
        folders = [folders.to_json() for folders in folders_group]
        files = [files.to_json() for files in files_group]

        return jsonify({'status': 'ok', 'path': folder_path.split('/')[1:], 'now_path': folder_path, 'file': files,
                        'folders': folders})


# 从回收站恢复文件
class RecoverFile(MethodView):
    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        file = request.form.get('key')

        user_id = session.get('user_id')
        if ',' in file:
            da = file.split(',')
            for file in da:
                key = int(file.split('.')[-1])
                if 'folder' in file:
                    fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                              DiskFolder.id == key).one_or_none()
                    vail_date = datetime.now()
                    fol.update_time = vail_date
                    fol.is_trash = 0
                    db.session.commit()


                elif 'file' in file:
                    fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                            DiskFile.id == key).one_or_none()
                    vail_date = datetime.now()
                    fil.update_time = vail_date
                    fil.is_trash = 0
                    db.session.commit()
                    use_size = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                    use_size.use_disk_size = use_size.use_disk_size + fil.file_size
                    db.session.commit()

                else:
                    return jsonify({'status': 'error', 'msg': 'ERROR'})
            return jsonify({'status': 'ok', 'msg': '文件恢复成功'})
        else:
            key = int(file.split('.')[-1])
            if 'folder' in file:
                fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                          DiskFolder.id == key).one_or_none()
                vail_date = datetime.now()
                fol.update_time = vail_date
                fol.is_trash = 0
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': '文件恢复成功'})
            elif 'file' in file:
                fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id, DiskFile.id == key).one_or_none()
                vail_date = datetime.now()
                fil.update_time = vail_date
                fil.is_trash = 0
                db.session.commit()
                use_size = db.session.query(UseLog).filter(UseLog.user_id == user_id).one_or_none()
                use_size.use_disk_size = use_size.use_disk_size + fil.file_size
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': '文件恢复成功'})
            else:
                return jsonify({'status': 'error', 'msg': 'ERROR'})


# 彻底删除文件
class DropFile(MethodView):
    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        file = request.form.get('key')

        user_id = session.get('user_id')
        if ',' in file:
            da = file.split(',')
            for file in da:
                key = int(file.split('.')[-1])
                if 'folder' in file:
                    fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                              DiskFolder.id == key).one_or_none()
                    db.session.delete(fol)
                    db.session.commit()

                    group_fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                                    DiskFolder.group_id == fol.id).all()
                    if group_fol:
                        for fol in group_fol:
                            db.session.delete(fol)
                            db.session.commit()

                    group_fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                                  DiskFile.folder_group_id == fol.id).all()
                    if group_fil:
                        for fil in group_fil:
                            user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                                admin.models.Users.id == user_id).scalar()
                            filename = fil.file_name
                            file_path = f'static/disk{user_folder}/{filename}'
                            os.remove(file_path)
                            db.session.delete(fil)
                            db.session.commit()
                elif 'file' in file:
                    fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                            DiskFile.id == key).one_or_none()
                    user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                        admin.models.Users.id == user_id).scalar()
                    filename = fil.file_name
                    file_path = f'static/disk{user_folder}/{filename}'
                    os.remove(file_path)
                    db.session.delete(fil)
                    db.session.commit()
                else:
                    return jsonify({'status': 'error', 'msg': 'ERROR'})
            return jsonify({'status': 'ok', 'msg': '删除成功'})
        else:
            key = int(file.split('.')[-1])
            if 'folder' in file:
                fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                          DiskFolder.id == key).one_or_none()
                db.session.delete(fol)
                db.session.commit()
                db.session.commit()

                group_fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                                DiskFolder.group_id == fol.id).all()
                if group_fol:
                    for fol in group_fol:
                        db.session.delete(fol)
                        db.session.commit()

                group_fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                              DiskFile.folder_group_id == fol.id).all()
                if group_fil:
                    for fil in group_fil:
                        user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                            admin.models.Users.id == user_id).scalar()
                        filename = fil.file_name
                        file_path = f'static/disk{user_folder}/{filename}'
                        os.remove(file_path)
                        db.session.delete(fil)
                        db.session.commit()
                return jsonify({'status': 'ok', 'msg': '删除成功'})
            elif 'file' in file:
                fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id, DiskFile.id == key).one_or_none()
                user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                    admin.models.Users.id == user_id).scalar()
                filename = fil.file_name
                file_path = f'static/disk{user_folder}/{filename}'
                os.remove(file_path)
                db.session.delete(fil)
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': '删除成功'})
            else:
                return jsonify({'status': 'error', 'msg': 'ERROR'})


class GroupFolder(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        user_id = session.get('user_id')
        user = admin.models.db.session.query(admin.models.Users).filter(admin.models.Users.id == user_id).one_or_none()
        if user:
            if 0 <= user.authority <= 2:
                return render_template('manage/group.html')
            else:
                return 'NO AUTHORITY'
        else:
            return 'ERROR'

    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        user_id = session.get('user_id')
        user = admin.models.db.session.query(admin.models.Users).filter(admin.models.Users.id == user_id).one_or_none()
        if user:
            if 0 <= user.authority <= 1:
                folders = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                              DiskFolder.is_user_group == 1).all()

                return jsonify({'status': 'ok', 'folder': [fol.to_json() for fol in folders]})
            elif user.authority == 2:
                if user.user_group_id:
                    folders = db.session.query(DiskFolder).filter(DiskFolder.user_id == user.user_group_id,
                                                                  DiskFolder.is_user_group == 1).all()
                    return jsonify({'status': 'ok', 'folder': [fol.to_json() for fol in folders]})
                else:
                    return jsonify({'status': 'error', 'msg': '您还没有加入群组，请通过途径申请加入~'})
            else:
                return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            return jsonify({'status': 'error', 'msg': 'user is valid'})


class AddGroup(MethodView):
    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        user_id = session.get('user_id')
        user = admin.models.db.session.query(admin.models.Users).filter(admin.models.Users.id == user_id).one_or_none()
        if user:
            if 0 <= user.authority <= 1:
                names = request.form.get('name')
                if names:
                    if len(names) > 30:
                        return jsonify({'status': 'error', 'msg': 'str length error'})
                    else:
                        check_fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                                        DiskFolder.folder_name == names).one_or_none()
                        if check_fol:
                            return jsonify({'status': 'error', 'msg': '名称重复，换一个吧'})
                        else:
                            ti = datetime.now()
                            fols = DiskFolder(folder_name=names, folder_path=f'/disk/{names}', user_id=user_id,
                                              is_user_group=1, creat_time=ti, update_time=ti, group_id=0)
                            db.session.add(fols)
                            db.session.commit()
                            return jsonify({'status': 'ok', 'msg': 'ok'})
                else:
                    return jsonify({'status': 'error', 'msg': 'user is valid'})
            else:
                return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            return jsonify({'status': 'error', 'msg': 'user is valid'})


class DelGroup(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        key = request.args.get('key')
        user_id = session.get('user_id')
        user = admin.models.db.session.query(admin.models.Users).filter(admin.models.Users.id == user_id).one_or_none()
        if user.authority in [0, 1]:
            fil = db.session.query(DiskFile).filter(DiskFile.user_id == user_id,
                                                    DiskFile.id == key).one_or_none()
            user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                admin.models.Users.id == user_id).scalar()
            filename = fil.file_name
            file_path = f'static/disk{user_folder}/{filename}'
            os.remove(file_path)
            db.session.delete(fil)
            db.session.commit()
            return jsonify({'status': 'ok', 'msg': 'ok'})
        else:
            return jsonify({'status': 'error', 'msg': '您无此权限'})

    def post(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})

        user_id = session.get('user_id')
        user = admin.models.db.session.query(admin.models.Users).filter(admin.models.Users.id == user_id).one_or_none()
        if user:
            if user.authority in [0, 1]:
                fol_id = request.form.get('key')
                check_fol = db.session.query(DiskFolder).filter(DiskFolder.user_id == user_id,
                                                                DiskFolder.id == fol_id).one_or_none()
                db.session.delete(check_fol)
                db.session.commit()
                return jsonify({'status': 'ok', 'msg': 'user is valid'})
            else:
                return jsonify({'status': 'error', 'msg': 'user is valid'})
        else:
            return jsonify({'status': 'error', 'msg': 'user is valid'})


class GroupDownload(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        fileid = request.args.get('key')
        user_id = session.get('user_id')
        user = admin.models.db.session.query(admin.models.Users).filter(
            admin.models.Users.id == user_id).one_or_none()
        if user.authority in [0, 1]:
            file = db.session.query(DiskFile).filter(DiskFile.user_id == user_id, DiskFile.id == fileid,
                                                     DiskFile.is_trash == 0).one_or_none()
            user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                admin.models.Users.id == user_id).scalar()
            path = f'static/disk{user_folder}/{file.file_name}'
            with open(path, 'rb') as f:
                data = f.read()

            resp = make_response(data)
            name = urllib.parse.quote(file.show_name)

            resp.headers["Content-Disposition"] = f"attachment; filename*=utf-8''{name}"
            resp.headers["Content-Type"] = f"application/octet-stream; charset=utf-8"

            return resp
        else:
            user_group = admin.models.db.session.query(admin.models.Users).filter(
                admin.models.Users.id == user.user_group_id).one_or_none()

            file = db.session.query(DiskFile).filter(DiskFile.user_id == user_group.id, DiskFile.id == fileid,
                                                     DiskFile.is_trash == 0).one_or_none()
            user_folder = admin.models.db.session.query(admin.models.Users.real_folder).filter(
                admin.models.Users.id == user_group.id).scalar()
            path = f'static/disk{user_folder}/{file.file_name}'
            with open(path, 'rb') as f:
                data = f.read()
            if '.txt' in file.file_name:
                data = data[0: 3000] + f'[{user_id}]'.encode() + data[3000:5000] + f'[{user_id}]'.encode() + data[5000:]
            resp = make_response(data)
            name = urllib.parse.quote(file.show_name)

            resp.headers["Content-Disposition"] = f"attachment; filename*=utf-8''{name}"
            resp.headers["Content-Type"] = f"application/octet-stream; charset=utf-8"

            return resp


class ClearShare(MethodView):
    def get(self):
        check_user = check_login()
        if check_user is None:
            return jsonify({'status': 'error', 'msg': 'no authority'})
        if check_user == -1:
            return jsonify({'status': 'error', 'msg': 'user is valid'})
        user_id = session.get('user_id')
        share = db.session.query(ShareGroups).filter(ShareGroups.user_id == user_id).all()
        if share:
            for sh in share:
                db.session.delete(sh)
                db.session.commit()
            return jsonify({'status': 'ok', 'msg': 'clear all'})
        else:
            return jsonify({'status': 'ok', 'msg': 'clear all'})