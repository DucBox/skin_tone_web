import io
import os
import tempfile
import unittest
import zipfile
import json
from unittest.mock import patch

os.environ.setdefault("MPLCONFIGDIR", "/private/tmp/skin-tone-mpl")

import cv2
import numpy as np
from openpyxl import load_workbook
from app import web_app
from app.history_store import HistoryStore


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        env = {"HISTORY_DIR": self.directory.name,
               "ADMIN_EMAIL": "admin", "ADMIN_PASSWORD": "correct horse battery"}
        self.environment = patch.dict(os.environ, env)
        self.environment.start()
        web_app.history_store.cache_clear()
        web_app.app.config["TESTING"] = True
        self.client = web_app.app.test_client()
        self.client.get("/")
        with self.client.session_transaction() as session:
            self.token = session["csrf_token"]
        login = self.client.post("/admin/login", data={
            "csrf_token": self.token, "username": "admin", "password": "correct horse battery"})
        self.assertEqual(login.status_code, 302)
        self.photo = np.full((80, 60, 3), 120, dtype=np.uint8)
        self.png = cv2.imencode(".png", self.photo)[1].tobytes()
        self.analysis = patch.object(web_app, "analyze_image_array", return_value={
            "ok": True, "message": "Thành công", "original_image": self.photo,
            "visualization_image": self.photo,
            "faces": [{"left_lstar": 60, "right_lstar": 62, "average_lstar": 61,
                       "skin_tone_group": {"group": 2, "label": "Vàng sáng / Olive nhạt", "range_text": "57-70"}}],
        })
        self.analyzer = self.analysis.start()

    def tearDown(self):
        self.analysis.stop()
        self.environment.stop()
        web_app.history_store.cache_clear()
        self.directory.cleanup()

    def upload(self, name, client=None, token=None):
        return (client or self.client).post("/", data={"csrf_token": token or self.token,
            "single_image": (io.BytesIO(self.png), name)}, content_type="multipart/form-data")

    def visitor(self):
        client = web_app.app.test_client()
        client.get("/")
        with client.session_transaction() as session:
            return client, session["csrf_token"]

    def test_history_survives_separate_uploads_and_store_restart_and_embeds_originals(self):
        self.assertEqual(self.upload("portrait-one.png").status_code, 200)
        self.assertEqual(self.upload("=unsafe-name.png").status_code, 200)
        web_app.history_store.cache_clear()
        store = web_app.history_store()
        self.assertEqual(len(store.ids()), 2)
        self.assertEqual(store.read(store.key(store.ids()[0], "original")), self.png)
        for kind in ("original", "preview"):
            image_response = self.client.get(f"/history/{store.ids()[0]}/image/{kind}")
            self.assertEqual(image_response.data, self.png)
            self.assertNotIn("attachment", image_response.headers.get("Content-Disposition", ""))
        with self.assertRaises(FileNotFoundError):
            store.read(store.key(store.ids()[0], "preview.jpg"))
        history = self.client.get("/history")
        self.assertIn("portrait-one.png", history.get_data(as_text=True))
        self.assertIn("=unsafe-name.png", history.get_data(as_text=True))
        self.assertIn('id="photo-preview"', history.get_data(as_text=True))
        self.assertIn('data-photo-src=', history.get_data(as_text=True))
        download = self.client.get("/history/export.xlsx")
        self.assertEqual(download.status_code, 200)
        raw = download.data
        workbook = load_workbook(io.BytesIO(raw))
        sheet = workbook.active
        self.assertEqual((sheet.max_row, sheet.max_column), (3, 4))
        self.assertEqual(sheet["A2"].data_type, "s")
        self.assertEqual(sheet["B2"].value, 61)
        self.assertEqual(sheet["C2"].value, "57-70")
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            media = [name for name in archive.namelist() if name.startswith("xl/media/")]
            self.assertEqual(len(media), 2)
            self.assertTrue(all(archive.read(name) == self.png for name in media))

    def test_delete_removes_only_target_row_and_its_images(self):
        self.upload("one.png")
        self.upload("two.png")
        store = web_app.history_store()
        first, second = store.ids()
        self.assertEqual(self.client.post(f"/history/{first}/delete").status_code, 400)
        response = self.client.post(f"/history/{first}/delete", data={"csrf_token": self.token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.ids(), [second])
        for name in ("record.json", "original", "preview.jpg", "visualization.jpg"):
            with self.assertRaises(FileNotFoundError):
                store.read(store.key(first, name))
        self.assertEqual(self.client.get(f"/history/{first}/image/preview").status_code, 404)

    def test_save_failure_is_not_reported_as_saved(self):
        with patch.object(HistoryStore, "put", side_effect=RuntimeError("storage unavailable")):
            response = self.upload("failure.png")
        html = response.get_data(as_text=True)
        self.assertIn("Có kết quả chưa lưu", html)
        self.assertIn("Chưa lưu lịch sử", html)
        self.assertEqual(web_app.history_store().ids(), [])

    def test_incomplete_s3_config_does_not_fall_back_to_local(self):
        with patch.dict(os.environ, {"S3_BUCKET_NAME": "test", "S3_ENDPOINT_URL": "",
                                   "S3_ACCESS_KEY_ID": "", "S3_SECRET_ACCESS_KEY": "", "S3_REGION": ""}):
            with self.assertRaises(RuntimeError):
                HistoryStore()

    def test_delete_all_requires_csrf_and_preserves_new_uploads(self):
        for i in range(3):
            self.upload(f"old-{i}.png")
        store = web_app.history_store()
        old_ids = store.ids()
        self.assertEqual(self.client.post("/history/delete-all").status_code, 400)
        self.upload("new.png")
        new_id = store.ids()[0]
        with patch.object(store, "ids", return_value=old_ids):
            response = self.client.post("/history/delete-all", data={"csrf_token": self.token})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(store.ids(), [new_id])
        response = self.client.post("/history/delete-all", data={"csrf_token": self.token}, follow_redirects=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(store.ids(), [])
        self.assertEqual(list((store.root / store.PREFIX).glob("*/*")), [])

    def test_pagination_and_invalid_id(self):
        for i in range(21):
            self.upload(f"photo-{i}.png")
        self.assertEqual(self.client.get("/history").get_data(as_text=True).count('class="history-photo"'), 20)
        self.assertEqual(self.client.get("/history?page=2").get_data(as_text=True).count('class="history-photo"'), 1)
        for size, expected in (("10", 10), ("20", 20), ("50", 21), ("100", 21), ("all", 21)):
            html = self.client.get(f"/history?per_page={size}").get_data(as_text=True)
            self.assertEqual(html.count('class="history-photo"'), expected)
            self.assertIn(f'value="{size}" selected', html)
        self.assertEqual(self.client.get("/history").get_data(as_text=True).count('class="history-photo"'), 21)
        html = self.client.get("/history?per_page=10&page=2").get_data(as_text=True)
        self.assertIn("per_page=10", html)
        self.assertEqual(html.count('class="history-photo"'), 10)
        self.assertEqual(self.client.get("/history?per_page=invalid").get_data(as_text=True).count('class="history-photo"'), 20)
        self.assertEqual(self.client.get("/history/not-an-id/image/preview").status_code, 404)

    def test_visitors_only_see_their_own_history_and_cannot_use_admin_actions(self):
        mine, mine_token = self.visitor()
        other, other_token = self.visitor()
        self.upload("admin-photo.png")
        self.upload("mine.png", mine, mine_token)
        self.upload("other.png", other, other_token)
        store = web_app.history_store()
        self.assertEqual(len(store.ids()), 3)
        with mine.session_transaction() as session:
            mine_owner = session["owner"]
        (mine_record,) = store.ids(mine_owner)
        self.assertEqual(store.get(mine_record)["file_name"], "mine.png")

        html = mine.get("/history").get_data(as_text=True)
        self.assertIn("mine.png", html)
        self.assertNotIn("other.png", html)
        self.assertNotIn("admin-photo.png", html)
        self.assertNotIn("Xuất Excel", html)
        self.assertNotIn("delete-button", html)
        admin_html = self.client.get("/history").get_data(as_text=True)
        for name in ("mine.png", "other.png", "admin-photo.png"):
            self.assertIn(name, admin_html)

        self.assertEqual(mine.get(f"/history/{mine_record}/image/preview").status_code, 200)
        foreign = next(i for i in store.ids() if i != mine_record)
        for kind in ("original", "preview", "visualization"):
            self.assertEqual(mine.get(f"/history/{foreign}/image/{kind}").status_code, 404)
        self.assertEqual(web_app.app.test_client().get(f"/history/{mine_record}/image/preview").status_code, 404)

        for client, token in ((mine, mine_token), (web_app.app.test_client(), "x")):
            self.assertEqual(client.get("/history/export.xlsx").status_code, 302)
            for path in (f"/history/{mine_record}/delete", "/history/delete-all"):
                response = client.post(path, data={"csrf_token": token})
                self.assertIn(response.status_code, (302, 400))
        self.assertEqual(len(store.ids()), 3)

    def test_admin_login_rejects_bad_credentials_and_is_disabled_without_config(self):
        visitor, token = self.visitor()
        bad = visitor.post("/admin/login", data={"csrf_token": token, "username": "admin", "password": "wrong"})
        self.assertEqual(bad.status_code, 401)
        self.assertEqual(visitor.get("/history/export.xlsx").status_code, 302)
        with patch.dict(os.environ, {"ADMIN_EMAIL": "", "ADMIN_PASSWORD": ""}):
            blank = visitor.post("/admin/login", data={"csrf_token": token, "username": "", "password": ""})
        self.assertEqual(blank.status_code, 401)
        self.assertEqual(visitor.post("/admin/login", data={"username": "admin", "password": "correct horse battery"}).status_code, 400)
        self.client.post("/admin/logout", data={"csrf_token": self.token})
        self.assertEqual(self.client.get("/history/export.xlsx").status_code, 302)

    def test_legacy_records_without_owner_are_admin_only_and_delete_cleans_index(self):
        visitor, token = self.visitor()
        store = web_app.history_store()
        item = web_app.build_item_result("legacy.png", self.analyzer.return_value)
        legacy = store.save(item, self.png, "image/png", None, self.png)["id"]
        self.assertNotIn("owner", store.get(legacy))
        self.upload("visitor.png", visitor, token)
        with visitor.session_transaction() as session:
            owner = session["owner"]
        (visitor_record,) = store.ids(owner)
        self.assertEqual(visitor.get(f"/history/{legacy}/image/preview").status_code, 404)
        self.assertEqual(self.client.get(f"/history/{legacy}/image/preview").status_code, 200)
        self.assertNotIn("legacy.png", visitor.get("/history").get_data(as_text=True))
        self.client.post(f"/history/{visitor_record}/delete", data={"csrf_token": self.token})
        self.assertEqual(store.ids(owner), [])
        self.assertEqual(list((store.root / store.OWNER_PREFIX).glob("*/*")), [])

    def test_result_page_is_vietnamese_and_minimal(self):
        html = self.upload("portrait.png").get_data(as_text=True)
        for gone in ("Bản test", "Group ", "CSV", "Tham chiếu", "Ngưỡng nhóm", "modal-note",
                     "L* má trái", "L* má phải", "Original image", "Visualization"):
            self.assertNotIn(gone, html)
        self.assertIn("Nhóm 2", html)
        self.assertIn("Thông tin kết quả", html)
        self.assertIn("Vàng sáng / Olive nhạt", html)
        self.assertFalse(self.analyzer.call_args.kwargs["draw_labels"])

    def test_error_pages_are_vietnamese_and_login_has_password_toggle(self):
        missing = self.client.get("/history/not-an-id/image/preview")
        self.assertEqual(missing.status_code, 404)
        self.assertIn("Không tìm thấy", missing.get_data(as_text=True))
        self.assertNotIn("Not Found", missing.get_data(as_text=True))
        login = self.visitor()[0].get("/admin/login").get_data(as_text=True)
        self.assertIn('id="toggle-password"', login)
        self.assertIn("Tài khoản", login)
        self.assertNotIn('type="email"', login)

    def test_owner_id_exists_before_first_upload_and_survives_parallel_first_saves(self):
        visitor, token = self.visitor()
        with visitor.session_transaction() as session:
            owner = session["owner"]
        self.assertRegex(owner, r"^[a-f0-9]{32}$")
        # Two uploads sent with the same (cookie-less-of-new-state) session keep one owner.
        self.upload("tab-one.png", visitor, token)
        self.upload("tab-two.png", visitor, token)
        with visitor.session_transaction() as session:
            self.assertEqual(session["owner"], owner)
        self.assertEqual(len(web_app.history_store().ids(owner)), 2)
        self.assertNotIn("tab-one.png", web_app.app.test_client().get("/history").get_data(as_text=True))

    def test_original_download_keeps_filename_and_respects_ownership(self):
        mine, mine_token = self.visitor()
        other, other_token = self.visitor()
        self.upload("ảnh chân dung.png", mine, mine_token)
        self.upload("other.png", other, other_token)
        store = web_app.history_store()
        with mine.session_transaction() as session:
            (own,) = store.ids(session["owner"])
        history = mine.get("/history").get_data(as_text=True)
        self.assertIn("Tải ảnh gốc", history)
        self.assertIn(f"/history/{own}/image/original?download=1", history)
        download = mine.get(f"/history/{own}/image/original?download=1")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.data, self.png)
        self.assertIn("attachment", download.headers["Content-Disposition"])
        self.assertEqual(self.client.get(f"/history/{own}/image/original?download=1").status_code, 200)
        foreign = next(i for i in store.ids() if i != own and store.get(i)["file_name"] == "other.png")
        self.assertEqual(mine.get(f"/history/{foreign}/image/original?download=1").status_code, 404)
        inline = mine.get(f"/history/{own}/image/original")
        self.assertNotIn("attachment", inline.headers.get("Content-Disposition", ""))

    def test_signed_download_url_forces_attachment_with_utf8_name(self):
        settings = {"S3_BUCKET_NAME": "test-bucket", "S3_ENDPOINT_URL": "https://storage.example.test",
                    "S3_ACCESS_KEY_ID": "test-key", "S3_SECRET_ACCESS_KEY": "test-secret", "S3_REGION": "auto"}
        with patch.dict(os.environ, settings):
            store = HistoryStore()
        record_id = "20261022T134624481983Z-" + "a" * 32
        plain = store.signed_url(record_id, "original")
        named = store.signed_url(record_id, "original", download_name="ảnh\r\n\"x\".png")
        self.assertNotIn("response-content-disposition", plain)
        self.assertIn("response-content-disposition=attachment", named)
        self.assertIn("filename%2A%3DUTF-8%27%27%25E1%25BA%25A3nh", named)
        for raw in ("%0D", "%0A", "%22"):  # CR/LF/quote must stay percent-encoded inside the header value
            self.assertNotIn(raw, named)

    def test_s3_upload_list_read_and_delete_contract(self):
        from botocore.stub import Stubber, ANY
        from botocore.response import StreamingBody
        settings = {"S3_BUCKET_NAME": "test-bucket", "S3_ENDPOINT_URL": "https://storage.example.test",
                    "S3_ACCESS_KEY_ID": "test-key", "S3_SECRET_ACCESS_KEY": "test-secret", "S3_REGION": "auto"}
        with patch.dict(os.environ, settings):
            store = HistoryStore()
        with Stubber(store.client) as stub:
            for content_type in ("image/png", "image/jpeg", "image/jpeg", "application/json"):
                stub.add_response("put_object", {}, {"Bucket": "test-bucket", "Key": ANY,
                                                    "Body": ANY, "ContentType": content_type})
            item = web_app.build_item_result("photo.png", self.analyzer.return_value)
            record = store.save(item, self.png, "image/png", self.png, self.png)
            key = store.key(record["id"])
            stub.add_response("list_objects_v2", {"Contents": [{"Key": key}]},
                              {"Bucket": "test-bucket", "Prefix": store.PREFIX})
            self.assertEqual(store.ids(), [record["id"]])
            payload = json.dumps(record).encode()
            expected_get = {"Bucket": "test-bucket", "Key": key}
            for _ in range(2):
                stub.add_response("get_object", {"Body": StreamingBody(io.BytesIO(payload), len(payload))}, expected_get)
            self.assertEqual(store.get(record["id"])["average_lstar"], 61)
            stub.add_response("delete_objects", {}, {"Bucket": "test-bucket", "Delete": {
                "Objects": [{"Key": store.key(record["id"], name)} for name in ("original", "preview.jpg", "visualization.jpg")]}})
            stub.add_response("delete_objects", {}, {"Bucket": "test-bucket", "Delete": {"Objects": [{"Key": key}]}})
            store.delete(record["id"])
            stub.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
