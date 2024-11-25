import argparse
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field
from functools import cached_property
import logging
from typing import ClassVar, Dict, List

import modin.pandas as pd
import pandas as _pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class InputFileInfo:
    """Container class for input file."""
    input_file_path: str
    EXTRA_COLUMNS: ClassVar[List[str]] = field(
        default=[
            'Matched_Rule_ID',
            'Rule_ID',
            'GPAC_Asset_Class_Level1',
            'GPAC_Asset_Class_Level2',
            'GPAC_Asset_Class_Level3',
            'Keywords_Matched',
            'Rule_Source',
            'GPAC_Tag'
        ]
    )
    df: pd.DataFrame = field(init=False)
    base_columns: List[str] = field(init=False)

    def __post_init__(self):
        self.df = pd.read_csv(self.input_file_path, dtype=str)
        self.base_columns = deepcopy(self.df.columns.tolist())
        self.add_extra_columns()
        self.tokenise()

    @cached_property
    def base_columns_lowercase(self) -> List[str]:
        """Get base column in lowercase."""
        return [
            s.lower() for s in self.base_columns
        ]

    @cached_property
    def output_columns(self) -> List[str]:
        """Get output file columns."""
        return self.base_columns + self.EXTRA_COLUMNS

    def add_extra_columns(self):
        """Add classification columns to dataframe."""
        for new_column in self.EXTRA_COLUMNS:
            if new_column not in self.df:
                if new_column == 'GPAC_Tag':
                    self.df[new_column] = 'unclassified'
                else:
                    self.df[new_column] = pd.NA

    def tokenise(self):
        """Tokenise all cels in a row into a new column."""
        self.df['tokenized'] = pd.Series(self.df.fillna('').values.astype(str).tolist()).str.join('#').str.lower()


@dataclass
class Classifier:
    """Classifier class."""
    mapping_source_path: str
    HIGH_PRIORITY_RULES_SHEET: ClassVar[str] = 'HG Rules'
    ASSET_CLASS_SHEET: ClassVar[str] = 'GPAC_ASSET_CLASS_LEVELS'

    @cached_property
    def high_priority_rules(self) -> OrderedDict[str, Dict]:
        """Get high priority rules mapping."""
        hpr = OrderedDict()

        for _, row in pd.DataFrame(
            _pd.read_excel(
                self.mapping_source_path,
                sheet_name=self.HIGH_PRIORITY_RULES_SHEET,
                dtype=str
            )
        ).sort_values(by='Priority', ascending=False).iterrows():
            rule_id = row['Rule ID']
            hpr[rule_id] = {
                'type': {
                    col.lstrip().rstrip()
                    for col in row['Column Group'].split(',')
                },
                'values_to_look_for': {
                    col.lstrip().rstrip().lower()
                    for col in row['Values to Look For'].split(',')
                },
                'asset_class_level_1': row['GPAC_ASSET_CLASS_LEVEL1'],
                'asset_class_level_2': row['GPAC_ASSET_CLASS_LEVEL2'],
                'asset_class_level_3': row['GPAC_ASSET_CLASS_LEVEL3'],
                **({'flag_values': row['Flag Value'].split(' ')} if 'flag_columns' in row['Column Group'] else {})
            }

        return hpr

    @cached_property
    def asset_class_mapping(self) -> Dict[str, Dict]:
        """Get asset class mapping."""
        ac = {}

        for _, row in pd.DataFrame(
                _pd.read_excel(
                    self.mapping_source_path,
                    sheet_name=self.ASSET_CLASS_SHEET,
                    dtype=str
                )
        ).iterrows():
            if pd.isnull(row['Rule_ID']):  # TODO: can we classify without rule id?
                continue
            rule_id = str(row['Rule_ID'])
            ac[rule_id] = {}
            if not pd.isnull(row['Keywords_Matched']):
                ac[rule_id]['values_to_look_for'] = {
                    col.lstrip().rstrip().replace('"', '').lower()  # TODO: case sensitive?
                    for col in row['Keywords_Matched'].split(',')
                    if not pd.isnull(col)
                }
            else:
                ac[rule_id]['values_to_look_for'] = set()
            ac[rule_id]['asset_class_level_1'] = row['GPAC_ASSET_CLASS_LEVEL1']
            ac[rule_id]['asset_class_level_2'] = row['GPAC_ASSET_CLASS_LEVEL2']
            ac[rule_id]['asset_class_level_3'] = row['GPAC_ASSET_CLASS_LEVEL3']

        return ac

    @staticmethod
    def get_series_classified(
            keyword: str,
            rule_id: str,
            rule_info: Dict
    ) -> pd.Series:
        """Get classified Series object."""
        return pd.Series(
            [
                rule_id,
                rule_id,
                rule_info['asset_class_level_1'],
                rule_info['asset_class_level_2'],
                rule_info['asset_class_level_3'],
                keyword,
                'GPAC Master',
                'classified',
            ]
        )

    @staticmethod
    def get_series_unclassified() -> pd.Series:
        """Get unclassified Series object."""
        return pd.Series([pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, 'unclassified'])

    @staticmethod
    def get_unchanged_series(row: pd.Series) -> pd.Series:
        """Get unchanged Series object."""
        return pd.Series(
            [
                row['Matched_Rule_ID'],
                row['Rule_ID'],
                row['GPAC_Asset_Class_Level1'],
                row['GPAC_Asset_Class_Level2'],
                row['GPAC_Asset_Class_Level3'],
                row['Keywords_Matched'],
                row['Rule_Source'],
                row['GPAC_Tag']
            ]
        )

    @staticmethod
    def hpr_func(
            row: pd.Series,
            hpr: OrderedDict[str, Dict],
            base_columns: List[str],
            base_column_lowercase: List[str]
    ) -> pd.Series:
        """Classify a row per high priority rules."""
        for rule_id, rule_info in hpr.items():
            if 'flag_columns' in rule_info['type']:
                for val_to_check in rule_info['values_to_look_for']:
                    for col_name, col_name_lower in zip(base_columns, base_column_lowercase):
                        if val_to_check in col_name_lower:
                            if row[col_name] in rule_info['flag_values']:
                                return Classifier.get_series_classified(val_to_check, rule_id, rule_info)
            if 'string_columns' in rule_info['type']:
                for val_to_check in rule_info['values_to_look_for']:
                    if val_to_check in row['tokenized']:
                        return Classifier.get_series_classified(val_to_check, rule_id, rule_info)
        return Classifier.get_series_unclassified()

    @staticmethod
    def ac_func(row: pd.Series, ac: Dict) -> pd.Series:
        """Classify one row per asset classification mapping."""
        if row['GPAC_Tag'] == 'classified':
            return Classifier.get_unchanged_series(row)

        for rule_id, rule_info in ac.items():
            for val_to_check in rule_info['values_to_look_for']:
                if val_to_check in row['tokenized']:
                    return Classifier.get_series_classified(val_to_check, rule_id, rule_info)
        return Classifier.get_series_unclassified()

    def classify(self, input_file_path: str, output_file_path: str) -> None:
        """Classify input file and save to output file."""
        # Read and pre-process input file.
        logger.info(f'Pre-processing input file {input_file_path}')
        input_file = InputFileInfo(input_file_path)

        # Classify per HR Rules
        logger.info('Classifying per High Priority Rules.')
        input_file.df[InputFileInfo.EXTRA_COLUMNS] = input_file.df.apply(
            lambda row: self.hpr_func(
                row,
                self.high_priority_rules,
                input_file.base_columns,
                input_file.base_columns_lowercase
            ),
            axis=1
        )

        # Classify per GPAC Asset Classification
        logger.info('Classifying per asset classification.')
        input_file.df[InputFileInfo.EXTRA_COLUMNS] = input_file.df.apply(
            lambda row: self.ac_func(
                row,
                self.high_priority_rules
            ),
            axis=1
        )

        # Write output file
        logger.info(f'Saving output to {output_file_path}.')
        input_file.df[input_file.output_columns].to_csv(output_file_path, index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mapping-file', help="C:/Users/aksha/OneDrive/Desktop/Ulyses/GPAC Master-8.xlsx")
    parser.add_argument('--input-file', help="C:/Users/aksha/OneDrive/Desktop/Ulyses/SMART_20240912.csv")
    parser.add_argument('--output-file', help="C:/Users/aksha/OneDrive/Desktop/Ulyses/SMART_20240912_OUTPUT.csv")
    args = parser.parse_args()

    try:
        classifier = Classifier(args.mapping_file)
        classifier.classify(args.input_file, args.output_file)
    except Exception as e:
        logger.info('Encountered exception. Please contact support.')
        logger.exception(e)


if __name__ == '__main__':
    main()