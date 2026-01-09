package com.wonjun.mentormatch.dto.certification;

import com.wonjun.mentormatch.domain.Member;
import com.wonjun.mentormatch.domain.member.Certification;
import com.wonjun.mentormatch.domain.member.CertificationType;
import lombok.Getter;
import lombok.NoArgsConstructor;

@Getter
@NoArgsConstructor
public class CertificationSaveRequestDto {
    private CertificationType type;
    private String imageBase64;

    public Certification toEntity(Member member) {
        return new Certification(member, type, imageBase64);
    }
}
