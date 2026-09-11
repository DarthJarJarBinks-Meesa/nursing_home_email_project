import pandas as pd


def main() -> None:
    input_file = "Nursery Homes.csv"
    output_file = "nursing_homes_deduplicated.csv"

    columns_to_keep = [
        "CMS Certification Number (CCN)",
        "Provider Name",
        "Provider Address",
        "City/Town",
        "State",
        "ZIP Code",
        "Location",
        "Processing Date",
    ]

    df = pd.read_csv(input_file)
    df_deduplicated = (
        df[columns_to_keep]
        .drop_duplicates(subset=["CMS Certification Number (CCN)"], keep="first")
        .reset_index(drop=True)
    )

    df_deduplicated.to_csv(output_file, index=False)
    print(f"Saved {len(df_deduplicated)} rows to {output_file}")


if __name__ == "__main__":
    main()
