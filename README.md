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
- Chinh `brightness scale` o ban dev
- Xem anh goc
- Xem anh visualization
- Xem `L*` ma trai, `L*` ma phai, `L*` cuoi, nhom mau da
- Xuat CSV

Ghi chu:
- `brightness scale` chi anh huong den backend tinh `L*`
- Anh goc va visualization van dung anh goc
- Production co the an field nay va set co dinh qua env `APP_BRIGHTNESS_SCALE`

### Cach 2: chay web bang Docker

Dockerfile nay la ban don gian cho local/web app, khong dung cho flow server noi bo.

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
  --image-type live \
  --brightness-scale 0.90
```

Vi du chi thong ke anh `portrait_` trong `Non-Match`:

```bash
python3 app/batch_folder_report.py \
  --input-dir /duong/dan/toi/root_folder \
  --output-dir /duong/dan/toi/folder_ket_qua \
  --match-type non-match \
  --image-type portrait \
  --brightness-scale 1.00
```

Gia tri `--brightness-scale`:
- `1.0`: giu nguyen do sang
- `< 1.0`: giam sang truoc khi tinh `L*`
- `> 1.0`: tang sang truoc khi tinh `L*`

Luu y:
- Brightness chi tac dong den backend tinh `L*`
- Visualization van luu tren anh goc

### File output cua batch

Trong thu muc output se co:
- `tong_hop_ket_qua.csv`
- `phan_phoi_nhom_da.png`
- `phan_phoi_gia_tri_lstar.png`
- `ty_le_pass_fail.png`
- `visualizations/...`

## 3. Chay batch bang Docker

Phan nay moi la flow Docker danh cho server noi bo. Neu can base image, proxy, pip registry noi bo thi truyen qua `--build-arg`.

Build:

```bash
docker build -f Dockerfile.batch \
  --build-arg BASE_IMAGE=10.30.154.118:8989/nvidia/pytorch:25.10-py3 \
  --build-arg http_proxy=http://10.30.153.169:3128 \
  --build-arg https_proxy=http://10.30.153.169:3128 \
  --build-arg PIP_INDEX_URL=http://10.30.154.118:8888/repository/Python/simple \
  --build-arg PIP_EXTRA_INDEX_URL=http://10.30.154.118:8888/repository/Python/ngc \
  --build-arg PIP_TRUSTED_HOST=10.30.154.118 \
  -t skin-tone-batch .
```

Run container:

```bash
docker run --rm -d \
  --name skin-tone-batch-job \
  -v /path/to/your/images:/mounted/input \
  -v /path/to/your/output:/mounted/output \
  skin-tone-batch
```

Exec vao container va chay lenh batch:

```bash
docker exec -it skin-tone-batch-job \
  python3 app/batch_folder_report.py \
  --input-dir /mounted/input \
  --output-dir /mounted/output \
  --match-type match \
  --image-type live \
  --brightness-scale 0.90
```

Ban chi can thay:
- `/path/to/your/images`: thu muc anh dau vao
- `/path/to/your/output`: thu muc muon luu ket qua

Neu xong viec va muon vao shell:

```bash
docker exec -it skin-tone-batch-job bash
```

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
