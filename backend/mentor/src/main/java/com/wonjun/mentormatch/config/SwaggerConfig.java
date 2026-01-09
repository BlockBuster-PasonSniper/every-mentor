package com.wonjun.mentormatch.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class SwaggerConfig {

    @Bean
    public OpenAPI openAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("멘토링 매칭 시스템 API")
                        .description("팀 프로젝트 API 명세서입니다.")
                        .version("1.0.0"));
    }
}