import argparse
from collections import OrderedDict, Counter
from copy import deepcopy
from dataclasses import dataclass, field
from functools import cached_property
import logging
from typing import ClassVar, Dict, List

import modin.pandas as pd
import pandas as _pd
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tokenize keywords function
def collect_keywords(input_file_path: str):
    """Collect and tokenize all keywords from the input file."""
    logger.info("Collecting and tokenizing keywords from input file...")
    df = _pd.read_csv(input_file_path, dtype=str)
    keyword_counter = Counter()

    for col in df.columns:
        df[col] = df[col].fillna('').astype(str)
        for cell in df[col]:
            tokens = re.findall(r'\b\w+\b', cell.lower())
            keyword_counter.update(tokens)

    keyword_list = [keyword for keyword, _ in keyword_counter.most_common()]
    logger.info(f"Total unique keywords collected: {len(keyword_list)}")
    logger.info(f"Sample keywords collected: {keyword_list[:10]} (showing first 10)")
    return keyword_list


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
            'GPAC_Tag',
            'Collected_Keywords'  # New column for collected keywords
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
        return [s.lower() for s in self.base_columns]

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
        """Tokenise all cells in a row into a new column."""
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
                    col.strip()
                    for col in row['Column Group'].split(',')
                },
                'values_to_look_for': {
                    col.strip().lower()
                    for col in row['Values to Look For'].split(',')
                },
                'asset_class_level_1': row['GPAC_ASSET_CLASS_LEVEL1'],
                'asset_class_level_2': row['GPAC_ASSET_CLASS_LEVEL2'],
                'asset_class_level_3': row['GPAC_ASSET_CLASS_LEVEL3'],
                **({'flag_values': row['Flag Value'].split(' ')} if 'flag_columns' in row['Column Group'] else {})
            }

        return hpr

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
                                return pd.Series(
                                    [rule_id, rule_id, rule_info['asset_class_level_1'],
                                     rule_info['asset_class_level_2'], rule_info['asset_class_level_3'],
                                     val_to_check, 'GPAC Master', 'classified']
                                )
            if 'string_columns' in rule_info['type']:
                for val_to_check in rule_info['values_to_look_for']:
                    if val_to_check in row['tokenized']:
                        return pd.Series(
                            [rule_id, rule_id, rule_info['asset_class_level_1'],
                             rule_info['asset_class_level_2'], rule_info['asset_class_level_3'],
                             val_to_check, 'GPAC Master', 'classified']
                        )
        return pd.Series([pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, pd.NA, 'unclassified'])

    def classify(self, input_file_path: str, output_file_path: str, keywords: List[str]) -> None:
        """Classify input file and save to output file."""
        logger.info(f'Pre-processing input file {input_file_path}')
        input_file = InputFileInfo(input_file_path)

        # Add collected keywords to the DataFrame
        input_file.df['Collected_Keywords'] = ', '.join(keywords)

        # Classify per HR Rules
        logger.info('Classifying per High Priority Rules.')
        input_file.df[InputFileInfo.EXTRA_COLUMNS[:-1]] = input_file.df.apply(
            lambda row: self.hpr_func(
                row,
                self.high_priority_rules,
                input_file.base_columns,
                input_file.base_columns_lowercase
            ),
            axis=1
        )

        logger.info(f'Saving output to {output_file_path}.')
        input_file.df[input_file.output_columns].to_csv(output_file_path, index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mapping-file', help="Path to mapping file.")
    parser.add_argument('--input-file', help="Path to input file to classify.")
    parser.add_argument('--output-file', help="Path to output classified file.")
    args = parser.parse_args()

    try:
        # Collect and tokenize keywords
        keywords = collect_keywords(args.input_file)
        logger.info(f"Tokenized keywords collected: {keywords[:10]} (showing first 10)")

        # Perform classification
        classifier = Classifier(args.mapping_file)
        classifier.classify(args.input_file, args.output_file, keywords)

    except Exception as e:
        logger.error("Encountered exception during execution.")
        logger.exception(e)


if __name__ == '__main__':
    main()
