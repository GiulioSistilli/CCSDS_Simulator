# xml_validator.py
import xml.etree.ElementTree as ET
from xmlschema import XMLSchema
import os
from pathlib import Path
from typing import Dict, Any, Optional
import json

class CCSDSXMLValidator:
    """Validator for CCSDS MO Services XML documents"""
    
    def __init__(self, schema_dir: str = None):
        self.schema_dir = schema_dir or os.path.dirname(__file__)
        self.schemas = {}
        self.load_schemas()
    
    def load_schemas(self):
        """Load all CCSDS schemas"""
        schema_files = {
            'common': 'ccsds_common_types.xsd',
            'mo': 'ccsds_mo_services.xsd'
        }
        
        for name, filename in schema_files.items():
            schema_path = os.path.join(self.schema_dir, filename)
            if os.path.exists(schema_path):
                self.schemas[name] = XMLSchema(schema_path)
    
    def validate_mo_xml(self, xml_content: str, operation: str) -> Dict[str, Any]:
        """Validate MO Service XML against schema"""
        try:
            # Parse XML
            root = ET.fromstring(xml_content)
            
            # Determine which schema to use
            if 'GetParameterValuesRequest' in root.tag:
                schema = self.schemas['mo']
                operation = 'GetParameterValuesRequest'
            elif 'GetParameterValuesResponse' in root.tag:
                schema = self.schemas['mo']
                operation = 'GetParameterValuesResponse'
            elif 'SetParameterValuesRequest' in root.tag:
                schema = self.schemas['mo']
                operation = 'SetParameterValuesRequest'
            elif 'SetParameterValuesResponse' in root.tag:
                schema = self.schemas['mo']
                operation = 'SetParameterValuesResponse'
            elif 'GetServiceInfoRequest' in root.tag:
                schema = self.schemas['mo']
                operation = 'GetServiceInfoRequest'
            elif 'GetServiceInfoResponse' in root.tag:
                schema = self.schemas['mo']
                operation = 'GetServiceInfoResponse'
            else:
                return {
                    "valid": False,
                    "errors": [f"Unknown operation type: {root.tag}"]
                }
            
            # Validate against schema
            schema.validate(xml_content)
            
            # Additional semantic validation
            validation_result = self._semantic_validation(root, operation)
            
            return {
                "valid": True,
                "operation": operation,
                "validation_result": validation_result
            }
            
        except Exception as e:
            return {
                "valid": False,
                "errors": [str(e)],
                "operation": operation
            }
    
    def _semantic_validation(self, root: ET.Element, operation: str) -> Dict[str, Any]:
        """Perform semantic validation beyond XML schema"""
        result = {
            "warnings": [],
            "recommendations": []
        }
        
        if 'GetParameterValuesRequest' in operation:
            # Check parameter list
            param_list = root.find('.//{*}parameterIdList')
            if param_list is not None:
                params = param_list.findall('.//{*}parameterId')
                if len(params) == 0:
                    result["warnings"].append("Parameter list is empty")
                if len(params) > 1000:
                    result["warnings"].append("Parameter list exceeds recommended limit of 1000")
        
        elif 'GetParameterValuesResponse' in operation:
            # Check timestamps
            timestamp = root.find('.//{*}timestamp')
            if timestamp is not None:
                # Validate timestamp format
                ts_text = timestamp.text
                if not ('Z' in ts_text or '+' in ts_text or '-' in ts_text):
                    result["warnings"].append("Timestamp should include timezone indicator")
            
            # Check result status
            result_elem = root.find('.//{*}result')
            if result_elem is not None:
                status = result_elem.find('.//{*}status')
                if status is not None and status.text == 'FAILURE':
                    error_code = result_elem.find('.//{*}errorCode')
                    if error_code is None:
                        result["warnings"].append("Failure result should include error code")
        
        return result
    
    def generate_sample_xml(self, operation: str) -> str:
        """Generate sample XML for a given operation"""
        samples = {
            'GetParameterValuesRequest': '''<?xml version="1.0" encoding="UTF-8"?>
<GetParameterValuesRequest 
    xmlns="http://www.ccsds.org/schema/Service/MonitorAndControl"
    xmlns:common="http://www.ccsds.org/schema/Common">
    <parameterIdList>
        <parameterId>TEMPERATURE_BUS</parameterId>
        <parameterId>VOLTAGE_BUS</parameterId>
        <parameterId>CURRENT_BUS</parameterId>
    </parameterIdList>
    <requestId>REQ_20241227_001</requestId>
    <qualityOfService>
        <priority>1</priority>
        <timeout>PT30S</timeout>
        <reliability>AT_LEAST_ONCE</reliability>
    </qualityOfService>
</GetParameterValuesRequest>''',
            
            'GetParameterValuesResponse': '''<?xml version="1.0" encoding="UTF-8"?>
<GetParameterValuesResponse 
    xmlns="http://www.ccsds.org/schema/Service/MonitorAndControl"
    xmlns:common="http://www.ccsds.org/schema/Common">
    <parameterList>
        <parameter>
            <parameterId>TEMPERATURE_BUS</parameterId>
            <parameterValue>
                <floatValue>25.5</floatValue>
            </parameterValue>
            <validity>VALID</validity>
            <generationTime>2024-12-27T10:30:45.123Z</generationTime>
            <qualityIndicator>GOOD</qualityIndicator>
        </parameter>
        <parameter>
            <parameterId>VOLTAGE_BUS</parameterId>
            <parameterValue>
                <floatValue>12.3</floatValue>
            </parameterValue>
            <validity>VALID</validity>
            <generationTime>2024-12-27T10:30:45.123Z</generationTime>
            <qualityIndicator>GOOD</qualityIndicator>
        </parameter>
    </parameterList>
    <requestId>REQ_20241227_001</requestId>
    <timestamp>2024-12-27T10:30:45.456Z</timestamp>
    <result>
        <status>SUCCESS</status>
    </result>
</GetParameterValuesResponse>''',
            
            'SetParameterValuesRequest': '''<?xml version="1.0" encoding="UTF-8"?>
<SetParameterValuesRequest 
    xmlns="http://www.ccsds.org/schema/Service/MonitorAndControl"
    xmlns:common="http://www.ccsds.org/schema/Common">
    <parameterSetList>
        <parameterSet>
            <parameterId>MODE_SELECTION</parameterId>
            <parameterValue>
                <stringValue>SCIENCE_MODE</stringValue>
            </parameterValue>
            <validityConstraint>
                <validFrom>2024-12-27T10:30:00Z</validFrom>
                <validUntil>2024-12-27T11:30:00Z</validUntil>
            </validityConstraint>
        </parameterSet>
    </parameterSetList>
    <requestId>CMD_20241227_001</requestId>
    <executionMode>VALIDATED</executionMode>
</SetParameterValuesRequest>''',
            
            'GetServiceInfoRequest': '''<?xml version="1.0" encoding="UTF-8"?>
<GetServiceInfoRequest 
    xmlns="http://www.ccsds.org/schema/Service/MonitorAndControl"
    xmlns:common="http://www.ccsds.org/schema/Common">
    <serviceIdentifier>
        <serviceName>MonitorAndControl</serviceName>
        <serviceVersion>2.0.0</serviceVersion>
    </serviceIdentifier>
    <requestId>INFO_001</requestId>
</GetServiceInfoRequest>'''
        }
        
        return samples.get(operation, '')
    
    def xml_to_dict(self, xml_content: str) -> Dict[str, Any]:
        """Convert XML to dictionary for easier processing"""
        try:
            root = ET.fromstring(xml_content)
            return self._element_to_dict(root)
        except Exception as e:
            return {"error": str(e)}
    
    def _element_to_dict(self, element: ET.Element) -> Dict[str, Any]:
        """Recursively convert XML element to dictionary"""
        result = {}
        
        # Handle attributes
        if element.attrib:
            result['@attributes'] = dict(element.attrib)
        
        # Handle child elements
        children = list(element)
        if children:
            for child in children:
                child_dict = self._element_to_dict(child)
                
                # Handle namespaced tags
                tag = child.tag
                if '}' in tag:
                    tag = tag.split('}')[1]
                
                # Handle multiple elements with same tag
                if tag in result:
                    if isinstance(result[tag], list):
                        result[tag].append(child_dict)
                    else:
                        result[tag] = [result[tag], child_dict]
                else:
                    result[tag] = child_dict
        else:
            # Leaf node with text
            if element.text and element.text.strip():
                result['#text'] = element.text.strip()
        
        return result
    
    def dict_to_xml(self, data: Dict[str, Any], root_tag: str) -> str:
        """Convert dictionary to CCSDS XML"""
        def dict_to_element(tag: str, value: Any) -> ET.Element:
            element = ET.Element(tag)
            
            if isinstance(value, dict):
                # Handle attributes
                if '@attributes' in value:
                    for attr, attr_value in value['@attributes'].items():
                        element.set(attr, str(attr_value))
                
                # Handle text content
                if '#text' in value:
                    element.text = str(value['#text'])
                
                # Handle child elements
                for child_tag, child_value in value.items():
                    if child_tag not in ['@attributes', '#text']:
                        if isinstance(child_value, list):
                            for item in child_value:
                                element.append(dict_to_element(child_tag, item))
                        else:
                            element.append(dict_to_element(child_tag, child_value))
            
            elif isinstance(value, list):
                for item in value:
                    element.append(dict_to_element('item', item))
            else:
                element.text = str(value)
            
            return element
        
        root = dict_to_element(root_tag, data)
        
        # Add namespaces
        root.set('xmlns', 'http://www.ccsds.org/schema/Service/MonitorAndControl')
        root.set('xmlns:common', 'http://www.ccsds.org/schema/Common')
        
        # Pretty print
        ET.indent(root, space="  ", level=0)
        xml_str = ET.tostring(root, encoding='unicode', xml_declaration=True)
        
        return xml_str

# Usage examples
if __name__ == "__main__":
    validator = CCSDSXMLValidator()
    
    # Generate sample XML
    sample = validator.generate_sample_xml('GetParameterValuesRequest')
    print("Sample GetParameterValuesRequest:")
    print(sample)
    print("\n" + "="*60 + "\n")
    
    # Validate sample
    result = validator.validate_mo_xml(sample, 'GetParameterValuesRequest')
    print("Validation Result:")
    print(json.dumps(result, indent=2))
    print("\n" + "="*60 + "\n")
    
    # Convert to dictionary
    xml_dict = validator.xml_to_dict(sample)
    print("XML as Dictionary:")
    print(json.dumps(xml_dict, indent=2))