# PSTC Workshop: Ring Difference-in-Differences with Geocoded Housing Data

This repository contains a minimal data pipeline that estimates the effect of a polluting plant's opening on nearby house prices with a ring difference-in-differences design. The notebook cleans ATTOM deed and tax assessor records, geocodes sales, draws rings around two Rhode Island plants that entered the EPA Toxics Release Inventory (TRI) in 2005, and compares average prices inside 1 km (treatment) and 1–2 km (control) before and after 2005.

Sean McCulloch, 12 October 2026

## Getting the code

Click the green **Code** button above and choose **Download ZIP**, then unzip it anywhere. If you use Git, `git clone` the repository instead.

Install the Python packages once:

```bash
pip install -r requirements.txt
```

## Getting the data

The housing data are licensed ATTOM data distributed through [Dewey](https://www.deweydata.io/), so they are not in this repository. Download them yourself with your own Dewey access:

1. **ATTOM Recorder** (deed transfers): Rhode Island, recording dates 2000–2010. Required columns: `APNFORMATTED`, `ARMSLENGTHFLAG`, `ATTOMID`, `PROPERTYUSEGROUP`, `PROPERTYUSESTANDARDIZED`, `RECORDINGDATE`, `TRANSACTIONID`, `TRANSACTIONTYPE`, `TRANSFERAMOUNT`.
2. **ATTOM Tax Assessor** (parcel coordinates): Rhode Island. Required columns: `ATTOMID`, `LATITUDE`, `LONGITUDE`.

Unzip the two downloads and rename the folders so the layout looks like this:

```
src/raw/recorder/   <- the recorder_*.csv.gz files
src/raw/assessor/   <- the tax-assessor_*.parquet files
src/raw/tri2005RIlist.csv   (included in this repository)
```

The TRI plant locations (`tri2005RIlist.csv`) are public EPA data and are included.

## Running the pipeline

Open `src/pgm/pstcworkshop.ipynb` in Jupyter and run all cells. All paths are relative to the notebook, so no edits are needed. Intermediate files are written to `bld/`, which the notebook creates. The CPI step downloads the series from FRED, so you need an internet connection.

## Folder structure

```
src/
  pgm/   notebook
  raw/   input data (ATTOM data you download + TRI plant list)
bld/     intermediate and output data (created when you run the notebook)
```

## Data note

Do not commit or share the ATTOM files or anything in `bld/`. The `.gitignore` excludes them, but check `git status` before you push.
