/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : STM32 HTS221 I2C + RGB(PA1) + Motor PWM & Speed(PA7)
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "dma.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <string.h>
#include <stdio.h>
/* USER CODE END Includes */

/* Private define ------------------------------------------------------------*/
#define RX_BUF_SIZE 128
#define PARSE_BUF_SIZE 256
#define HTS221_ADDR 0xBE // 8-bit I2C address (0x5F << 1)

/* Private variables ---------------------------------------------------------*/
extern I2C_HandleTypeDef hi2c1;
extern TIM_HandleTypeDef htim3;  /* 引入 CubeMX 生成的 TIM3 句柄 */

uint8_t rx_buf[RX_BUF_SIZE];
volatile uint16_t rx_len = 0;
volatile uint8_t rx_done = 0;
uint8_t parse_buf[PARSE_BUF_SIZE];
uint16_t parse_len = 0;

typedef enum { MOTOR_STOP = 0, MOTOR_FORWARD, MOTOR_REVERSE } MotorState_t;
MotorState_t motor_state = MOTOR_STOP;

/* 电机速度变量 */
uint8_t motor_speed = 50; 

volatile uint8_t rgb_color_idx = 0;

uint32_t last_upload_time = 0;

/* 中断消抖时间戳 */
volatile uint32_t pa1_exti_time = 0;     // PA1 (RGB控制)
volatile uint32_t key2_exti_time = 0;    // PA7 (调速控制)

uint8_t key1_last = 1;
uint32_t key1_time = 0;

/* HTS221 Calibration Data */
int16_t T0_out, T1_out, T0_degC, T1_degC;
int16_t H0_out, H1_out, H0_rh, H1_rh;

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
void Motor_Set(MotorState_t state);
void RGB_SetColor(uint8_t idx);
void Send_DeviceState(void);
extern void MX_I2C1_Init(void);

/* ==================== HTS221 传感器健壮驱动 ==================== */
void HTS221_Init(void)
{
    uint8_t who_am_i = 0;
    
    if (HAL_I2C_Mem_Read(&hi2c1, HTS221_ADDR, 0x0F, 1, &who_am_i, 1, 500) != HAL_OK || who_am_i != 0xBC)
    {
        T0_out = 0; T1_out = 0;
        return; 
    }

    uint8_t ctrl1 = 0x85; 
    HAL_I2C_Mem_Write(&hi2c1, HTS221_ADDR, 0x20, 1, &ctrl1, 1, 500);

    HAL_Delay(50); 

    uint8_t buf[16] = {0};
    if(HAL_I2C_Mem_Read(&hi2c1, HTS221_ADDR, 0x30 | 0x80, 1, buf, 16, 500) == HAL_OK)
    {
        H0_rh = buf[0] >> 1;
        H1_rh = buf[1] >> 1;
        T0_degC = ((buf[5] & 0x03) << 8 | buf[2]) >> 3;
        T1_degC = ((buf[5] & 0x0C) << 6 | buf[3]) >> 3;
        H0_out = (int16_t)(buf[7] << 8 | buf[6]);
        H1_out = (int16_t)(buf[11] << 8 | buf[10]);
        T0_out = (int16_t)(buf[13] << 8 | buf[12]);
        T1_out = (int16_t)(buf[15] << 8 | buf[14]);
    }
}

void HTS221_Read(float *temp, float *hum)
{
    if (T1_out == T0_out || H1_out == H0_out) 
    {
        *temp = -99.9f;
        *hum = -99.9f;
        return;
    }

    uint8_t buf[4] = {0};
    if(HAL_I2C_Mem_Read(&hi2c1, HTS221_ADDR, 0x28 | 0x80, 1, buf, 4, 100) != HAL_OK)
    {
        *temp = -99.9f;
        *hum = -99.9f;
        return;
    }
    
    int16_t h_out = (int16_t)(buf[1] << 8 | buf[0]);
    int16_t t_out = (int16_t)(buf[3] << 8 | buf[2]);

    *temp = T0_degC + ((float)(t_out - T0_out) / (T1_out - T0_out)) * (T1_degC - T0_degC);
    *hum = H0_rh + ((float)(h_out - H0_out) / (H1_out - H0_out)) * (H1_rh - H0_rh);
}

/* ==================== 协议发送与解析 ==================== */
void Send_SensorData(float temp, float hum)
{
    int16_t t = (int16_t)(temp * 10);
    int16_t h = (int16_t)(hum * 10);
    uint8_t buf[9] = {0x5A, 0xA5, 0x05, 0x01, (t >> 8), (t & 0xFF), (h >> 8), (h & 0xFF), 0};
    buf[8] = buf[2] ^ buf[3] ^ buf[4] ^ buf[5] ^ buf[6] ^ buf[7]; 
    HAL_UART_Transmit(&huart2, buf, 9, 100);
}

void Send_DeviceState(void)
{
    /* 上传增加了 motor_speed 字节，总长度变为 4 */
    uint8_t buf[8] = {0x5A, 0xA5, 0x04, 0x02, (uint8_t)motor_state, rgb_color_idx, motor_speed, 0};
    buf[7] = buf[2] ^ buf[3] ^ buf[4] ^ buf[5] ^ buf[6]; 
    HAL_UART_Transmit(&huart2, buf, 8, 100);
}

void HAL_UARTEx_RxEventCallback(UART_HandleTypeDef *huart, uint16_t Size)
{
    if(huart->Instance == USART2) { rx_len = Size; rx_done = 1; }
}

void UART2_RxStart(void)
{
    HAL_UARTEx_ReceiveToIdle_DMA(&huart2, rx_buf, RX_BUF_SIZE);
}

void UART2_ProcessProtocol(void)
{
    if(rx_done)
    {
        HAL_UART_DMAStop(&huart2); 
        for(uint16_t k = 0; k < rx_len; k++) {
            if(parse_len < PARSE_BUF_SIZE) parse_buf[parse_len++] = rx_buf[k];
        }
        rx_done = 0; rx_len = 0;
        UART2_RxStart();
        
        uint16_t i = 0;
        while(i + 3 < parse_len) 
        {
            if(parse_buf[i] == 0x5A && parse_buf[i+1] == 0xA5)
            {
                uint8_t data_len = parse_buf[i+2];
                if(i + 3 + data_len >= PARSE_BUF_SIZE) { i++; continue; }
                
                if(i + 3 + data_len < parse_len)
                {
                    uint8_t calc_checksum = data_len;
                    for(uint8_t j = 0; j < data_len; j++) calc_checksum ^= parse_buf[i + 3 + j];
                    
                    if(calc_checksum == parse_buf[i + 3 + data_len])
                    {
                        uint8_t cmd = parse_buf[i+3];
                        uint8_t *data = &parse_buf[i+4];
                        
                        /* 增加 0x0C 调速指令解析 */
                        if (cmd == 0x0A && data_len == 2) {
                            Motor_Set((MotorState_t)data[0]);
                            Send_DeviceState(); 
                        } else if (cmd == 0x0B && data_len == 2) {
                            RGB_SetColor(data[0]);
                            Send_DeviceState(); 
                        } else if (cmd == 0x0C && data_len == 2) {
                            motor_speed = data[0];
                            if(motor_speed > 100) motor_speed = 100;
                            Motor_Set(motor_state); // 更新PWM
                            Send_DeviceState(); 
                        }
                        
                        i += (4 + data_len);
                        continue;
                    }
                } else break; 
            }
            i++; 
        }
        
        if(i > 0) {
            parse_len -= i;
            memmove(parse_buf, &parse_buf[i], parse_len);
        }
        if(parse_len == PARSE_BUF_SIZE) parse_len = 0;
    }
}

/* ==================== 外设控制与中断 ==================== */
void Motor_Set(MotorState_t state)
{
    motor_state = state;
    uint32_t pulse = (uint32_t)motor_speed * 10;
    
    switch(state) {
        case MOTOR_STOP:
            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_3, 0); 
            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_4, 0); 
            break;
        case MOTOR_FORWARD:
            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_3, pulse); 
            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_4, 0);     
            break;
        case MOTOR_REVERSE:
            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_3, 0);     
            __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_4, pulse); 
            break;
    }
}

void RGB_SetColor(uint8_t idx)
{
    rgb_color_idx = idx % 8;
    GPIO_PinState r = (rgb_color_idx & 0x01) ? GPIO_PIN_RESET : GPIO_PIN_SET;
    GPIO_PinState g = (rgb_color_idx & 0x02) ? GPIO_PIN_RESET : GPIO_PIN_SET;
    GPIO_PinState b = (rgb_color_idx & 0x04) ? GPIO_PIN_RESET : GPIO_PIN_SET;

    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_2, r);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_10, g);
    HAL_GPIO_WritePin(GPIOB, GPIO_PIN_11, b);
}

void HAL_GPIO_EXTI_Callback(uint16_t GPIO_Pin)
{
    uint32_t cur = HAL_GetTick();
    
    /* PA1: RGB 颜色切换 */
    if(GPIO_Pin == GPIO_PIN_1) 
    {
        if(cur - pa1_exti_time > 200) {
            pa1_exti_time = cur;
            RGB_SetColor(rgb_color_idx + 1);
            Send_DeviceState(); 
        }
    }
    /* PA7: 电机速率调速 */
    else if(GPIO_Pin == GPIO_PIN_7) 
    {
        if(cur - key2_exti_time > 200) {
            key2_exti_time = cur;
            
            if(motor_state != MOTOR_STOP) 
            {
                motor_speed += 10;
                if(motor_speed > 100) motor_speed = 0;
                
                Motor_Set(motor_state); 
                Send_DeviceState(); // 通过协议将新速度同步给上位机
            }
        }
    }
}

void EXTI1_IRQHandler(void)
{
    HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_1);
}

void EXTI9_5_IRQHandler(void)
{
    HAL_GPIO_EXTI_IRQHandler(GPIO_PIN_7);
}

uint8_t Key1_Pressed(void)
{
    uint8_t key = HAL_GPIO_ReadPin(GPIOA, GPIO_PIN_6);
    if(key == 0 && key1_last == 1) {
        if(HAL_GetTick() - key1_time > 200) {
            key1_time = HAL_GetTick();
            key1_last = key;
            return 1;
        }
    }
    key1_last = key;
    return 0;
}
/* USER CODE END 0 */

int main(void)
{
  HAL_Init();
  SystemClock_Config();

  MX_GPIO_Init();
  MX_DMA_Init();
  MX_USART1_UART_Init();
  MX_USART2_UART_Init();
  MX_TIM1_Init();
  MX_TIM3_Init(); 
  MX_I2C1_Init(); 
  
  /* USER CODE BEGIN 2 */
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();
  
  GPIO_InitStruct.Pin = GPIO_PIN_2 | GPIO_PIN_10 | GPIO_PIN_11;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
  
  GPIO_InitStruct.Pin = GPIO_PIN_1 | GPIO_PIN_7;
  GPIO_InitStruct.Mode = GPIO_MODE_IT_FALLING;
  GPIO_InitStruct.Pull = GPIO_PULLUP;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
  
  HAL_NVIC_SetPriority(EXTI1_IRQn, 2, 0); 
  HAL_NVIC_EnableIRQ(EXTI1_IRQn);
  
  HAL_NVIC_SetPriority(EXTI9_5_IRQn, 2, 0); 
  HAL_NVIC_EnableIRQ(EXTI9_5_IRQn);
  
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_3);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_4);
  
  HTS221_Init();
  Motor_Set(MOTOR_STOP);
  RGB_SetColor(0); 
  UART2_RxStart();
  /* USER CODE END 2 */

  while (1)
  {
    UART2_ProcessProtocol();
    
    if(Key1_Pressed())
    {
        switch(motor_state) {
            case MOTOR_STOP:    Motor_Set(MOTOR_FORWARD); break;
            case MOTOR_FORWARD: Motor_Set(MOTOR_REVERSE); break;
            case MOTOR_REVERSE: Motor_Set(MOTOR_STOP); break;
            default:            Motor_Set(MOTOR_STOP); break;
        }
        Send_DeviceState(); 
    }
    
    if (HAL_GetTick() - last_upload_time > 1000)
    {
        last_upload_time = HAL_GetTick();
        float temp, hum;
        HTS221_Read(&temp, &hum);
        Send_SensorData(temp, hum);
    }
  }
}

void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.HSEPredivValue = RCC_HSE_PREDIV_DIV1;
  RCC_OscInitStruct.HSIState = RCC_HSI_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLMUL = RCC_PLL_MUL9;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) { Error_Handler(); }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK|RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV2;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) { Error_Handler(); }
}

void Error_Handler(void) { __disable_irq(); while (1) {} }

#ifdef USE_FULL_ASSERT
void assert_failed(uint8_t *file, uint32_t line) {}
#endif