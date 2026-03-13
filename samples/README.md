# Samples

This folder contains runnable Python examples for common `slmp4e` workflows.

The examples are meant to be friendlier than the maintainer-oriented scripts under [`scripts/`](../scripts/README.md):

- `samples/` shows application-side usage of the Python API
- `scripts/` contains verification and maintenance wrappers for this repository

## How To Run

Run the examples from the repository root:

```powershell
python samples/01_read_type_name.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

You can also install the package first:

```powershell
python -m pip install "git+https://github.com/fa-yoshinobu/slmp4e-connect-python.git"
```

## Safety

- all examples in this folder are read-only
- label examples depend on PLC-side label configuration and `Access from External Device`

## Example List

### 01. Basic connection and type name

```powershell
python samples/01_read_type_name.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

### 02. Normal device reads

```powershell
python samples/02_device_reads.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --word-device D100 --word-points 2 --bit-device M100 --bit-points 5
```

### 03. Random and block reads

```powershell
python samples/03_random_and_block.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr
```

### 05. Explicit target header

```powershell
python samples/05_target_header.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --network 0x00 --station 0xFF --module-io 0x03FF --multidrop 0x00
```

### 06. Label reads

```powershell
python samples/06_label_reads.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --label-random LabelW --label-random LabelB
```

Array-label example:

```powershell
python samples/06_label_reads.py --host 192.168.250.101 --port 1025 --transport tcp --series iqr --label-array "ArrayLabel[0]:1:4"
```
