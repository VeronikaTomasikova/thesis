#include <Arduino.h>
#include <Wire.h>                          // For I2C communication
#include <Adafruit_Sensor.h>               // For the unified sensor interface
#include "TCA9548.h"                       // for multiplexer
#include "I2C_EXT.h"                       // i2c library for ad5934 

#define START_FREQUENCY1 16900 //16620 tma//16737 //17480//17140 //17620 last frequencies with first multicantilever//17321 //for TMA      //og 11556 //14484 
#define START_FREQUENCY2 17235 //17440 cad//16550 //17295//16650 //17720 //16940 this works //17146 //for TMA      //og 11812 //16830 
#define START_FREQUENCY3 17330 //16500 nan//16468 //17560//15860 //17650 //17146 this works //17182 //for TMA      //og 11556 //


//Multiplexer instance
TCA9548 multiplexer(0x70); // Address for TCA9548 (default)

//AD5934 instances
AD5934 ad5934; //IC instance

//BME680 instance
Adafruit_BME680 bme;


float magnitudeData[3][NUM_INCREMENTS]; // 3 devices, NUM_INCREMENTS points per sweep 
float phaseData[3][NUM_INCREMENTS];


void setup() {
    Wire.begin();
    Serial.begin(115200);
    delay(6000);  // Give time for Serial monitor to initialize. adjust per your needs
    Serial.println("starting");

    if (!multiplexer.begin()){
        Serial.println("TCA9548 initialization failed!"); //to optimise i can put else/if etc to let it out of the loop when multiplexer is ready
        while (1);
    }
}

void loop() {

 String command = Serial.readString();

 if(command == "start" || command == "init_start"){

    for (int channel = 1; channel <=3; channel++){
            //Serial.println("Switching to channel ");
            //Serial.println(channel);

                multiplexer.selectChannel(channel);
                delay(50); // Allow channel to stabilize

                // Check if multiplexer connected to the AD5934
                if (!multiplexer.isConnected(AD5934_ADDR, channel))
                {
                    //Serial.print("Multiplexer failed to select channel ");
                    //Serial.println(channel);
                    continue; // Skip to next channel
                }

                unsigned long startFrequency;
                switch (channel)
                {
                    case 1:
                        startFrequency = START_FREQUENCY1;
                        break;
                    case 2:
                        startFrequency = START_FREQUENCY2;
                        break;
                    case 3:
                        startFrequency = START_FREQUENCY3;
                        break;
                }

                if (!ad5934.setupAD5934(startFrequency))
                {
                    Serial.print("Error initializing AD5934 on channel ");
                    Serial.println(channel);
                    continue; // Skip to next channel
                }
    
                ad5934.setPGAGain(1); //setting the gain either 1 or 5, can be commented later

                // Perform the sweep and process data
                SweepAndProcess(channel, ad5934, multiplexer, magnitudeData, phaseData, channel - 1); //channel -1 bc channel starts from 1 but array starts from 0


                //send the magnitude and phase data (print)

               /*for (int i = 0; i < NUM_INCREMENTS; i++) //prints 
                {
                    Serial.print(phaseData[channel - 1][i]);
                    Serial.println(",");
                    //Serial.print(magnitudeData[channel-1][i]);
                    //Serial.println(",");
                }*/


                delay(100); // Small delay before next channel

        }
    


        //const char* labels[2] = {"PHASE", "MAG"};

            for(int channel = 1; channel <= 3; channel++){ //loops through 3 channels
                //delay(10);
                for (int type = 0; type < 2; type++) { //switches between 2 arrays- phase and magnitude
                    float* dataRow = (type == 0) ? phaseData[channel-1] : magnitudeData[channel-1];

                    //Serial.print(labels[type]);
                    //Serial.print(channel);
                    //Serial.print(":");

                    for (int i = 0; i < NUM_INCREMENTS; i++){ //loops through each of the 501 measurements
                        Serial.print(dataRow[i]);
                        if(i!=NUM_INCREMENTS-1){
                            Serial.write(","); // writes "," in between measurements
                            delay(10);
                        }


                    }Serial.println(","); // writes \n as next line when loop reaches 501 measurements
                     delay(10);
                }
                 Serial.flush();    
            }
        
            //delay(1);
            //if(command == "start"){
            float temperature = 0;
            float humidity = 0;
            multiplexer.selectChannel(0);
            setupBME680(bme);  
            bme.performReading();
            temperature = bme.temperature;
            humidity = bme.humidity;

            //Serial.write(38); //should not be needed as after 3rd magnitude data sent it will go to next row again
            
            Serial.print(temperature);
            Serial.print("&");
            Serial.println(humidity);

            Serial.flush();
           // }
    }

    if (command == "temp"){
        float temperature = 0;
        float humidity = 0;
        multiplexer.selectChannel(0);
        setupBME680(bme);  
        bme.performReading();
        temperature = bme.temperature;
        humidity = bme.humidity;

        //Serial.write(38); //should not be needed as after 3rd magnitude data sent it will go to next row again
            
        Serial.print(temperature);
        Serial.print("&");
        Serial.println(humidity);

        Serial.flush();
    }
}
