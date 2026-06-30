# Skin Tone Tool

Tool phan nhom mau da tu anh chan dung, dua tren gia tri `L*` o 2 vung ma.

## 1. Chay web local

### Cach 1: chay bang Python

```bash
MPLCONFIGDIR=/private/tmp/mplconfig \
PYTHONPYCACHEPREFIX=/private/tmp/pycache \
python3 app/web_app.py
```

Mo:

```text
http://127.0.0.1:5001
```

Web hien ho tro:
- Tai 1 anh
- Tai ca folder anh
- Mo camera trong browser
- Xem anh goc
- Xem anh visualization
- Xem `L*` ma trai, `L*` ma phai, `L*` cuoi, nhom mau da
- Xuat CSV

### Cach 2: chay web bang Docker

Build:

```bash
docker build -t skin-tone-web-local .
```

Run:

```bash
docker run --rm -p 8091:8080 skin-tone-web-local
```

Mo:

```text
http://127.0.0.1:8091
```

## 2. Chay batch folder local

Script batch dung de xu ly ca 1 thu muc anh, luu visualization, xuat CSV, va ve 2 chart phan phoi.

Cau truc root folder du kien:

```text
root/
  Match/
    1/
      live_....jpg
      portrait_....jpg
    2/
      live_....jpg
      portrait_....jpg
  Non-Match/
    10001/
      live_....jpg
      portrait_....jpg
```

### Chay bang Python

```bash
MPLCONFIGDIR=/private/tmp/mplconfig \
PYTHONPYCACHEPREFIX=/private/tmp/pycache \
python3 app/batch_folder_report.py \
  --input-dir /duong/dan/toi/folder_anh \
  --output-dir /duong/dan/toi/folder_ket_qua
```

Co the doi mode:

```bash
python3 app/batch_folder_report.py \
  --input-dir /duong/dan/toi/folder_anh \
  --output-dir /duong/dan/toi/folder_ket_qua \
  --mode all
```

Gia tri `--mode`:
- `largest`: lay khuon mat lon nhat
- `all`: xu ly tat ca khuon mat

Gia tri `--match-type`:
- `all`: lay ca `Match` va `Non-Match`
- `match`: chi lay folder `Match`
- `non-match`: chi lay folder `Non-Match`

Gia tri `--image-type`:
- `all`: lay ca `live_` va `portrait_`
- `live`: chi lay anh bat dau bang `live_`
- `portrait`: chi lay anh bat dau bang `portrait_`

Vi du chi thong ke anh `live_` trong `Match`:

```bash
MPLCONFIGDIR=/private/tmp/mplconfig \
PYTHONPYCACHEPREFIX=/private/tmp/pycache \
python3 app/batch_folder_report.py \
  --input-dir /duong/dan/toi/root_folder \
  --output-dir /duong/dan/toi/folder_ket_qua \
  --match-type match \
  --image-type live
```

Vi du chi thong ke anh `portrait_` trong `Non-Match`:

```bash
python3 app/batch_folder_report.py \
  --input-dir /duong/dan/toi/root_folder \
  --output-dir /duong/dan/toi/folder_ket_qua \
  --match-type non-match \
  --image-type portrait
```

### File output cua batch

Trong thu muc output se co:
- `tong_hop_ket_qua.csv`
- `phan_phoi_nhom_da.png`
- `phan_phoi_gia_tri_lstar.png`
- `visualizations/...`

## 3. Chay batch bang Docker

Build:

```bash
docker build -f Dockerfile.batch -t skin-tone-batch .
```

Run:

```bash
docker run --rm \
  -v /path/to/your/images:/mounted/input \
  -v /path/to/your/output:/mounted/output \
  skin-tone-batch \
  --match-type match \
  --image-type live
```

Ban chi can thay:
- `/path/to/your/images`: thu muc anh dau vao
- `/path/to/your/output`: thu muc muon luu ket qua

## 4. Dinh dang anh duoc ho tro

- `.png`
- `.jpg`
- `.jpeg`
- `.webp`
- `.heic`
- `.heif`

## 5. Deploy Railway

Repo hien da co san:
- `Dockerfile`
- `Procfile`
- `start.sh`
- `railway.toml`

Flow co ban:
1. Connect Railway voi GitHub repo.
2. Chon service tu repo nay.
3. Redeploy.
4. Generate Domain de lay link `https`.

Luu y:
- Camera tren browser can `https` hoac `localhost`.
- Production dang dung `APP_TEST_MODE=0`.

## 6. Ghi chu nhanh

- `L* ma trai` va `L* ma phai` van duoc tinh rieng.
- `L* cuoi` hien tai la trung binh cua tat ca pixel trong ca 2 vung ma gop lai, khong con la `(trai + phai) / 2`.
