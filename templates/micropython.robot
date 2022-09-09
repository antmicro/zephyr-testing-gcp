*** Settings ***
Suite Setup     Setup
Suite Teardown  Teardown
Test Teardown   Test Teardown
Resource        ${RENODEKEYWORDS}
Test timeout	30 s

*** Test Cases ***
{{sample_name}} on {{board_name}}
    ${x}=                       Execute Command             include @${EXECDIR}/artifacts/{{board_name}}-{{sample_name}}/{{board_name}}-{{sample_name}}.resc
    Create Terminal Tester      sysbus.{{uart_name}}        timeout=15
    Write Char Delay            0.01
    Start Emulation
    Wait For Prompt On Uart     >>>	timeout=0.2
    Write Line To Uart          2+2
    Wait For Line On Uart       4
    Write Line To Uart          def compare(a, b): return True if a > b else False
    Write Line To Uart           
    Write Line To Uart          compare(3.2, 2.4)
    Wait For Line On Uart       True
    Write Line To Uart          compare(2.2, 5.8)
    Wait For Line On Uart       False
