from flask_wtf import FlaskForm
from wtforms import SelectField, StringField
from flask_wtf.file import FileField, FileRequired, FileAllowed
from wtforms.validators import DataRequired


# Upload Form
class UploadForm(FlaskForm):
    iz = SelectField('Alma IZ', coerce=str, validators=[DataRequired()])
    csv = FileField('CSV File', validators=[
        FileRequired(),
        FileAllowed(['csv',], 'CSV files only!')
    ])
    almafield = SelectField('Alma Field', choices=[
        'pid',
        'barcode',
        'creation_date',
        'modification_date',
        'base_status',
        'awaiting_reshelving',
        'reshelving_time',
        'physical_material_type',
        'policy',
        'provenance',
        'po_line',
        'issue_date',
        'is_magnetic',
        'arrival_date',
        'expected_arrival_date',
        'year_of_issue',
        'enumeration_a',
        'enumeration_b',
        'enumeration_c',
        'enumeration_d',
        'enumeration_e',
        'enumeration_f',
        'enumeration_g',
        'enumeration_h',
        'chronology_i',
        'chronology_j',
        'chronology_k',
        'chronology_l',
        'chronology_m',
        'break_indicator',
        'pattern_type',
        'linking_number',
        'type_of_unit',
        'description',
        'replacement_cost',
        'receiving_operator',
        'process_type',
        'work_order_type',
        'work_order_at',
        'inventory_number',
        'inventory_date',
        'inventory_price',
        'receive_number',
        'weeding_number',
        'weeding_date',
        'library',
        'location',
        'alternative_call_number',
        'alternative_call_number_type',
        'alt_number_source',
        'storage_location_id',
        'pages',
        'pieces',
        'public_note',
        'fulfillment_note',
        'due_date',
        'due_date_policy',
        'internal_note_1',
        'internal_note_2',
        'internal_note_3',
        'statistics_note_1',
        'statistics_note_2',
        'statistics_note_3',
        'requested',
        'edition',
        'imprint',
        'language',
        'library_details',
        'parsed_alt_call_number',
        'parsed_call_number',
        'parsed_issue_level_description',
        'title_abcnph',
        'physical_condition',
        'committed_to_retain',
        'retention_reason',
        'retention_note'
    ], default='internal_note_1', validators=[DataRequired()])


# Add/Edit Institution Form
class InstitutionForm(FlaskForm):
    name = StringField('Name', validators=[DataRequired()])
    code = StringField('Code', validators=[DataRequired()])
    apikey = StringField('API Key', validators=[DataRequired()])
