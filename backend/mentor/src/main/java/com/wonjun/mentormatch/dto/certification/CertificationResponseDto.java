package com.wonjun.mentormatch.dto.certification;

import com.wonjun.mentormatch.domain.member.Certification;
import com.wonjun.mentormatch.domain.member.CertificationType;
import lombok.Getter;

import java.time.LocalDateTime;

@Getter
public class CertificationResponseDto {
    private final Long id;
    private final Long memberId;
    private final CertificationType type;
    private final LocalDateTime createdAt;

    public CertificationResponseDto(Certification entity) {
        this.id = entity.getId();
        this.memberId = entity.getMember().getId();
        this.type = entity.getType();
        this.createdAt = entity.getCreatedAt();
    }
}
