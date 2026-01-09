package com.wonjun.mentormatch.dto.application;

import com.wonjun.mentormatch.domain.application.ApplicationStatus;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class ApplicationStatusUpdateRequestDto {
    private ApplicationStatus status;
}
