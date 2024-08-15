/*
   @file    LIS2DUXS12_FIFO_Polling.ino
   @author  STMicroelectronics
   @brief   Example to use the LIS2DUXS12 library with FIFO status in polling mode.
 *******************************************************************************
   Copyright (c) 2022, STMicroelectronics
   All rights reserved.

   This software component is licensed by ST under BSD 3-Clause license,
   the "License"; You may not use this file except in compliance with the
   License. You may obtain a copy of the License at:
                          opensource.org/licenses/BSD-3-Clause

 *******************************************************************************
*/
#include <LIS2DUXS12Sensor.h>

#define SENSOR_ODR 100.0f // In Hertz
#define ACC_FS 2 // In g
#define MEASUREMENT_TIME_INTERVAL (100000.0f/SENSOR_ODR) // In ms
#define FIFO_SAMPLE_THRESHOLD 30

LIS2DUXS12Sensor LIS2DUXS12(&Wire);
uint8_t status = 0;
int32_t acc_value[3];

void Read_FIFO_Data();

void setup() {
  
  Serial.begin(115200);
  Wire.begin();
    
  // Initialize LIS2DUXS12.
  LIS2DUXS12.begin();
  status |= LIS2DUXS12.Enable_X();  
  // Configure ODR and FS
  status |= LIS2DUXS12.Set_X_ODR(SENSOR_ODR);
  status |= LIS2DUXS12.Set_X_FS(ACC_FS);
  // Configure FIFO BDR
  status |= LIS2DUXS12.Set_FIFO_X_BDR(LIS2DUXS12_BDR_XL_ODR);
  // Set FIFO watermark level
  status |= LIS2DUXS12.Set_FIFO_Watermark_Level(FIFO_SAMPLE_THRESHOLD);
  // Set FIFO stop on watermark level
  status |= LIS2DUXS12.Set_FIFO_Stop_On_Fth(1);
  // Set FIFO in Continuous mode
  status |= LIS2DUXS12.Set_FIFO_Mode(LIS2DUXS12_STREAM_MODE);   
  if(status != 0) {
    Serial.println("LIS2DUXS12 Sensor failed to init/configure");
    while(1);
  }
  Serial.println("LIS2DUXS12 FIFO Demo");
}

void loop() {
  uint8_t fullStatus = 0;
  // If we reach the threshold we can empty the FIFO
  if(LIS2DUXS12.Get_FIFO_Watermark_Status(&fullStatus) != 0){
      Serial.println("LIS2DUXS12 Sensor failed to get full status");
      while(1);
  }
  if(fullStatus) {
    fullStatus = 0;
    // Empty the FIFO
    Read_FIFO_Data();
  }
  delay(MEASUREMENT_TIME_INTERVAL);
}


void Read_FIFO_Data()
{
  uint16_t i;
  uint16_t samples_to_read;
  
  // Check the number of samples inside FIFO
  if(LIS2DUXS12.Get_FIFO_Num_Samples(&samples_to_read) != 0){
      Serial.println("LIS2DUXS12 Sensor failed to get number of samples inside FIFO");
      while(1);
    }
  
  for (i = 0; i < samples_to_read; i++) {
    uint8_t tag;
    
    // Check the FIFO tag
    if(LIS2DUXS12.Get_FIFO_Tag(&tag) != 0){
      Serial.println("LIS2DUXS12 Sensor failed to get tag");
      while(1);
    }
    switch (tag) { 
      // If we have an acc tag, read the acc data
      case 2: {
          if(LIS2DUXS12.Get_FIFO_X_Axes(acc_value) != 0){
            Serial.println("LIS2DUXS12 Sensor failed to get accelerometer data");
            while(1);
          }
          Serial.print("Accel-X[mg]:");
          Serial.print(acc_value[0]);
          Serial.print(",Accel-Y[mg]:");
          Serial.print(acc_value[1]);
          Serial.print(",Accel-Z[mg]:");
          Serial.println(acc_value[2]);
          break;
        }
        
      // We can discard other tags
      default: {
          break;
        }
    }
  }
}
