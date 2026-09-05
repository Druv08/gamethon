// Protect the King - 2D. Reusable Paper2D top-down character base.

#include "Characters/PTKTopDownCharacter.h"

#include "Camera/CameraComponent.h"
#include "Components/PTKHealthComponent.h"
#include "DrawDebugHelpers.h"
#include "Engine/OverlapResult.h"
#include "Components/CapsuleComponent.h"
#include "Engine/CollisionProfile.h"
#include "Engine/Engine.h"
#include "Engine/LocalPlayer.h"
#include "EnhancedInputComponent.h"
#include "EnhancedInputSubsystems.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/SpringArmComponent.h"
#include "InputActionValue.h"
#include "PaperFlipbook.h"
#include "PaperFlipbookComponent.h"
#include "ProtectTheKing2D.h"

#include UE_INLINE_GENERATED_CPP_BY_NAME(PTKTopDownCharacter)

namespace PTKCharacterDefaults
{
	/** Depth axis of the 2D play plane. Movement is locked to world XZ. */
	static const FVector PlaneConstraintNormal(0.0f, 1.0f, 0.0f);

	/**
	 * Yaw that points the camera boom along +Y, placing the camera on the -Y
	 * side of the play plane.
	 *
	 * This is the ONLY side Paper2D sprites actually render from here - proven
	 * empirically: at yaw -90 (camera on +Y) the sprite is backface-culled and
	 * completely invisible, while at yaw +90 it renders. Do not "correct" this
	 * to -90; that is what made the character disappear.
	 *
	 * Viewing from this side does mirror the texture horizontally, because
	 * PaperAxisX maps texture-right to world +X while this camera's right
	 * vector is world -X. That mirroring is undone by SpriteMirrorScaleX below,
	 * NOT by moving the camera.
	 */
	static constexpr float CameraBoomYaw = 90.0f;

	/**
	 * Horizontal flip applied to the sprite component to cancel the mirroring
	 * described above, so left-facing art reads as left-facing on screen.
	 */
	static constexpr float SpriteMirrorScaleX = -1.0f;

	/** Fallback movement basis, used only if the camera rig is missing. */
	static const FVector FallbackScreenRight(-1.0f, 0.0f, 0.0f);
	static const FVector FallbackScreenUp(0.0f, 0.0f, 1.0f);
	static const FVector FallbackScreenDepth(0.0f, 1.0f, 0.0f);
}

APTKTopDownCharacter::APTKTopDownCharacter(const FObjectInitializer& ObjectInitializer)
	// This is a 2D game: there is no skeletal mesh anywhere in Protect the King.
	// Skipping the subobject entirely keeps every character free of unused
	// skeletal machinery instead of merely hiding it.
	: Super(ObjectInitializer.DoNotCreateDefaultSubobject(ACharacter::MeshComponentName))
{
	PrimaryActorTick.bCanEverTick = true;
	PrimaryActorTick.bStartWithTickEnabled = true;

	// The camera is fixed to the world; the controller never rotates the pawn.
	bUseControllerRotationPitch = false;
	bUseControllerRotationYaw = false;
	bUseControllerRotationRoll = false;

	// ---------------------------------------------------------------
	// Collision: the gameplay footprint, not the silhouette.
	// ---------------------------------------------------------------
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->InitCapsuleSize(CollisionRadius, CollisionHalfHeight);
		Capsule->SetCollisionProfileName(UCollisionProfile::Pawn_ProfileName);
	}

	// ---------------------------------------------------------------
	// Paper2D visual.
	// ---------------------------------------------------------------
	Sprite = CreateDefaultSubobject<UPaperFlipbookComponent>(TEXT("Sprite"));
	if (Sprite)
	{
		Sprite->SetupAttachment(GetCapsuleComponent());
		Sprite->SetCollisionProfileName(UCollisionProfile::NoCollision_ProfileName);
		Sprite->SetGenerateOverlapEvents(false);
		Sprite->PrimaryComponentTick.TickGroup = TG_PrePhysics;

		// Zero rotation already faces a camera that looks along +Y, so the
		// sprite is never rotated to express direction - flipbooks do that.
		Sprite->SetRelativeRotation(FRotator::ZeroRotator);
		Sprite->SetRelativeLocation(FVector::ZeroVector);
		// Cancels the horizontal mirroring caused by the camera side. See
		// SpriteMirrorScaleX.
		Sprite->SetRelativeScale3D(
			FVector(PTKCharacterDefaults::SpriteMirrorScaleX, 1.0f, 1.0f));

		Sprite->CastShadow = false;
		Sprite->bCastDynamicShadow = false;
		Sprite->bReceivesDecals = false;
		Sprite->SetLooping(true);
	}

	// ---------------------------------------------------------------
	// Movement: free 2D motion across the XZ plane, no gravity, no floor.
	// ---------------------------------------------------------------
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->GravityScale = 0.0f;
		Move->DefaultLandMovementMode = MOVE_Flying;

		Move->MaxFlySpeed = MaxMoveSpeed;
		Move->MaxAcceleration = MoveAcceleration;
		Move->BrakingDecelerationFlying = MoveDeceleration;
		Move->bUseSeparateBrakingFriction = true;
		Move->BrakingFriction = 0.0f;
		Move->BrakingFrictionFactor = 1.0f;

		// Lock every character to the 2D play plane (Y = 0).
		Move->bConstrainToPlane = true;
		Move->bSnapToPlaneAtStart = true;
		Move->SetPlaneConstraintNormal(PTKCharacterDefaults::PlaneConstraintNormal);
		Move->SetPlaneConstraintOrigin(FVector::ZeroVector);

		// Never physically turn the actor - facing is purely visual.
		Move->bOrientRotationToMovement = false;
		Move->bUseControllerDesiredRotation = false;
		Move->RotationRate = FRotator::ZeroRotator;
	}

	// ---------------------------------------------------------------
	// Orthographic follow camera looking down +Y.
	// ---------------------------------------------------------------
	CameraBoom = CreateDefaultSubobject<USpringArmComponent>(TEXT("CameraBoom"));
	if (CameraBoom)
	{
		CameraBoom->SetupAttachment(GetCapsuleComponent());
		CameraBoom->TargetArmLength = CameraDistance;

		// Yaw 90 makes the boom point along +Y, so the camera sits at -Y and
		// looks back toward the play plane - straight at the sprite fronts.
		CameraBoom->SetUsingAbsoluteRotation(true);
		CameraBoom->SetRelativeRotation(FRotator(0.0f, PTKCharacterDefaults::CameraBoomYaw, 0.0f));

		CameraBoom->bDoCollisionTest = false;
		CameraBoom->bUsePawnControlRotation = false;
		CameraBoom->bInheritPitch = false;
		CameraBoom->bInheritYaw = false;
		CameraBoom->bInheritRoll = false;

		CameraBoom->bEnableCameraLag = bUseCameraLag;
		CameraBoom->CameraLagSpeed = CameraLagSpeed;
		CameraBoom->bEnableCameraRotationLag = false;
	}

	TopDownCamera = CreateDefaultSubobject<UCameraComponent>(TEXT("TopDownCamera"));
	if (TopDownCamera)
	{
		TopDownCamera->SetupAttachment(CameraBoom, USpringArmComponent::SocketName);
		TopDownCamera->bUsePawnControlRotation = false;

		// Orthographic is the correct projection for pixel art: sprite size is
		// constant regardless of depth, and the depth offsets used for sorting
		// produce no parallax at all.
		TopDownCamera->ProjectionMode = ECameraProjectionMode::Orthographic;
		TopDownCamera->OrthoWidth = CameraOrthoWidth;

		// Explicit clip planes so depth-sort offsets can never be clipped.
		TopDownCamera->bAutoCalculateOrthoPlanes = false;
		TopDownCamera->OrthoNearClipPlane = 0.0f;
		TopDownCamera->OrthoFarClipPlane = 100000.0f;

		// ---------------------------------------------------------------
		// LOCK EXPOSURE. Without this the character is literally invisible.
		//
		// Unreal's exposure is calibrated for physically-based light values.
		// Paper2D sprites use an UNLIT material, so their colour goes straight
		// to the scene as values in the 0..1 range - roughly 500x darker than
		// the real-world luminances the auto/manual exposure pipeline expects.
		// The sprite is drawn correctly and then tonemapped down to pure black,
		// while the UI (which bypasses exposure) still renders at full
		// brightness, making it look like the sprite failed to render at all.
		//
		// Forcing min == max == 1.0 pins the exposure multiplier at exactly 1,
		// so an unlit pixel authored as 1.0 reaches the screen as 1.0. This is
		// the correct setup for any unlit 2D game and is not a workaround.
		// ---------------------------------------------------------------
		TopDownCamera->PostProcessSettings.bOverride_AutoExposureMinBrightness = true;
		TopDownCamera->PostProcessSettings.AutoExposureMinBrightness = 1.0f;
		TopDownCamera->PostProcessSettings.bOverride_AutoExposureMaxBrightness = true;
		TopDownCamera->PostProcessSettings.AutoExposureMaxBrightness = 1.0f;
		TopDownCamera->PostProcessSettings.bOverride_AutoExposureBias = true;
		TopDownCamera->PostProcessSettings.AutoExposureBias = 0.0f;
	}

	// Health lives on a component rather than on the character so enemies,
	// guards, the King and any future destructible share one implementation.
	HealthComponent = CreateDefaultSubobject<UPTKHealthComponent>(TEXT("Health"));
}

void APTKTopDownCharacter::OnConstruction(const FTransform& Transform)
{
	Super::OnConstruction(Transform);

	// Re-apply designer-facing values so tuning them updates the editor viewport.
	ApplyCollisionAndSpriteSettings();
	UpdateMovementBasis();
}

void APTKTopDownCharacter::BeginPlay()
{
	Super::BeginPlay();

	FacingDirection = DefaultFacingDirection;
	MovementState = EPTKMovementState::Idle;
	PreviousMovementState = EPTKMovementState::Idle;

	if (HealthComponent)
	{
		HealthComponent->OnHealthChanged.AddDynamic(this, &APTKTopDownCharacter::HandleHealthChanged);
		HealthComponent->OnDeath.AddDynamic(this, &APTKTopDownCharacter::HandleDeathEvent);
	}
	MoveInput = FVector2D::ZeroVector;

	ApplyCollisionAndSpriteSettings();
	UpdateMovementBasis();

	UE_LOG(LogPTK, Log,
		TEXT("%s movement basis: screen-right=(%.2f, %.2f, %.2f)  screen-up=(%.2f, %.2f, %.2f)"),
		*GetName(),
		MovementRightVector.X, MovementRightVector.Y, MovementRightVector.Z,
		MovementUpVector.X, MovementUpVector.Y, MovementUpVector.Z);

	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		// Guarantee flying even if the pawn was spawned before a controller
		// existed, otherwise a gravity-less character can sit in MOVE_Walking
		// with no floor and refuse to move.
		Move->SetMovementMode(MOVE_Flying);
	}

	if (!bEnableCameraRig)
	{
		if (TopDownCamera)
		{
			TopDownCamera->Deactivate();
			TopDownCamera->SetActive(false);
		}
		if (CameraBoom)
		{
			CameraBoom->Deactivate();
		}
	}

	ValidateFlipbookConfiguration();

	// Show the correct idle frame on the very first tick.
	UpdateAnimation();
	UpdateDepthSorting();
}

void APTKTopDownCharacter::Tick(float DeltaSeconds)
{
	Super::Tick(DeltaSeconds);

	// A dead character holds its last frame and stops responding to anything.
	// Returning before the state machine is what guarantees a corpse cannot
	// walk, attack, or be pushed into a new animation by leftover input.
	if (MovementState == EPTKMovementState::Dead)
	{
		return;
	}

	const bool bMoving = MoveInput.SizeSquared() > FMath::Square(MoveDeadZone);

	// An attack owns the character until its flipbook has played through.
	// Resolving it before the walk/idle rules is the whole of "do NOT let
	// normal Walk/Idle logic immediately override it": while TickAttack still
	// claims the character, neither the facing nor the state below can run,
	// so the swing always completes and always ends in the direction it began.
	if (TickAttack(DeltaSeconds))
	{
		if (!bLockFacingDuringAttack && bMoving)
		{
			FacingDirection = UPTKTypesLibrary::DirectionFromInput(
				MoveInput, FacingDirection, MoveDeadZone, FacingHysteresis);
		}
	}
	else
	{
		// Facing is only ever updated while there is input. That single rule is
		// what makes the character keep his last direction when he stops:
		// releasing every key leaves FacingDirection exactly as it was.
		if (bMoving)
		{
			FacingDirection = UPTKTypesLibrary::DirectionFromInput(
				MoveInput, FacingDirection, MoveDeadZone, FacingHysteresis);
		}

		// The attack hands back to whichever state the player is actually in:
		// Walk if a key is still held, Idle otherwise - in the facing the
		// attack ended with.
		MovementState = bMoving ? EPTKMovementState::Walk : EPTKMovementState::Idle;
	}

	UpdateAnimation();
	UpdateDepthSorting();

	if (!bLoggedStartupDiagnostics && bShowDebugState)
	{
		bLoggedStartupDiagnostics = true;
		LogStartupDiagnostics();
	}

	if (bShowDebugState && GEngine)
	{
		// Cast is required: GetUniqueID() returns uint32, which converts equally
		// well to both the int32 and uint64 overloads of this function.
		GEngine->AddOnScreenDebugMessage(
			static_cast<uint64>(GetUniqueID()), 0.0f, FColor::Green,
			FString::Printf(
				TEXT("%s | %s | %s | input=(%+.2f, %+.2f) | vel=(%+.0f, %+.0f) screen(R,U) | speed=%.0f"),
				*GetName(),
				(MovementState == EPTKMovementState::Attack) ? TEXT("Attack")
					: (MovementState == EPTKMovementState::Walk) ? TEXT("Walk") : TEXT("Idle"),
				*UPTKTypesLibrary::DirectionToString(FacingDirection),
				MoveInput.X, MoveInput.Y,
				// Velocity projected onto the screen basis, so a positive first
				// number always means "moving right on screen".
				FVector::DotProduct(GetVelocity(), MovementRightVector),
				FVector::DotProduct(GetVelocity(), MovementUpVector),
				GetVelocity().Size()));
	}
}

void APTKTopDownCharacter::SetMoveInput(FVector2D NewInput)
{
	// Clamp the magnitude to 1 rather than normalising it.
	//
	//  - Keyboard W+A arrives as (-1, 1), length 1.414, and is scaled down to
	//    length 1, so diagonal movement is exactly as fast as cardinal
	//    movement instead of ~41% faster.
	//  - A gamepad stick pushed halfway arrives at length 0.5 and is left
	//    untouched, so analog speed control works with no extra code.
	const float SizeSq = NewInput.SizeSquared();
	MoveInput = (SizeSq > 1.0f) ? (NewInput / FMath::Sqrt(SizeSq)) : NewInput;

	if (MoveInput.SizeSquared() > FMath::Square(MoveDeadZone))
	{
		// Applied immediately (not deferred to Tick) so the movement component
		// consumes this input on the same frame it arrived.
		//
		// The basis comes from the camera rather than from a hardcoded axis -
		// see UpdateMovementBasis().
		AddMovementInput(MovementRightVector, MoveInput.X);
		AddMovementInput(MovementUpVector, MoveInput.Y);
	}
}

void APTKTopDownCharacter::LogStartupDiagnostics()
{
	UE_LOG(LogPTK, Warning, TEXT("===== PTK STARTUP DIAGNOSTICS (%s) ====="), *GetName());

	UE_LOG(LogPTK, Warning, TEXT("  actor location   = %s"), *GetActorLocation().ToString());

	if (Sprite)
	{
		UPaperFlipbook* Current = Sprite->GetFlipbook();
		const FBoxSphereBounds SpriteBounds = Sprite->Bounds;
		UE_LOG(LogPTK, Warning, TEXT("  sprite flipbook  = %s"),
			Current ? *Current->GetName() : TEXT("<NULL - nothing to draw>"));
		UE_LOG(LogPTK, Warning, TEXT("  sprite visible   = %d   hiddenInGame = %d   world loc = %s"),
			Sprite->IsVisible() ? 1 : 0,
			Sprite->bHiddenInGame ? 1 : 0,
			*Sprite->GetComponentLocation().ToString());
		UE_LOG(LogPTK, Warning, TEXT("  sprite bounds    = origin %s  extent %s"),
			*SpriteBounds.Origin.ToString(), *SpriteBounds.BoxExtent.ToString());
		UE_LOG(LogPTK, Warning, TEXT("  sprite rel rot   = %s   rel loc = %s"),
			*Sprite->GetRelativeRotation().ToString(),
			*Sprite->GetRelativeLocation().ToString());
	}
	else
	{
		UE_LOG(LogPTK, Error, TEXT("  SPRITE COMPONENT IS NULL"));
	}

	if (CameraBoom)
	{
		UE_LOG(LogPTK, Warning, TEXT("  boom world loc   = %s   world rot = %s   arm = %.1f"),
			*CameraBoom->GetComponentLocation().ToString(),
			*CameraBoom->GetComponentRotation().ToString(),
			CameraBoom->TargetArmLength);
	}

	if (TopDownCamera)
	{
		UE_LOG(LogPTK, Warning,
			TEXT("  camera world loc = %s   world rot = %s"),
			*TopDownCamera->GetComponentLocation().ToString(),
			*TopDownCamera->GetComponentRotation().ToString());
		UE_LOG(LogPTK, Warning,
			TEXT("  camera ortho     = %d   width = %.1f   near = %.1f   far = %.1f   active = %d"),
			TopDownCamera->ProjectionMode == ECameraProjectionMode::Orthographic ? 1 : 0,
			TopDownCamera->OrthoWidth,
			TopDownCamera->OrthoNearClipPlane,
			TopDownCamera->OrthoFarClipPlane,
			TopDownCamera->IsActive() ? 1 : 0);
	}

	// Is the engine actually looking through our camera component?
	if (const APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		const AActor* ViewTarget = PC->GetViewTarget();
		UE_LOG(LogPTK, Warning, TEXT("  view target      = %s  (this actor = %s)"),
			ViewTarget ? *ViewTarget->GetName() : TEXT("<none>"), *GetName());

		FVector CamLoc;
		FRotator CamRot;
		PC->GetPlayerViewPoint(CamLoc, CamRot);
		UE_LOG(LogPTK, Warning, TEXT("  ACTUAL viewpoint = %s   rot = %s"),
			*CamLoc.ToString(), *CamRot.ToString());
	}
	else
	{
		UE_LOG(LogPTK, Error, TEXT("  NOT POSSESSED BY A PLAYER CONTROLLER"));
	}

	UE_LOG(LogPTK, Warning, TEXT("========================================"));
}

void APTKTopDownCharacter::UpdateMovementBasis()
{
	// WHY THIS EXISTS
	// ---------------
	// Screen-space movement must never assume a world axis. It has to be read
	// from the camera, because the camera's orientation is dictated by which way
	// Paper2D sprites actually face - see CameraBoomYaw above.
	//
	// Deriving the basis here means movement, depth sorting and the view cannot
	// disagree, even if the rig is re-oriented later.
	MovementRightVector = PTKCharacterDefaults::FallbackScreenRight;
	MovementUpVector = PTKCharacterDefaults::FallbackScreenUp;
	MovementDepthVector = PTKCharacterDefaults::FallbackScreenDepth;

	if (CameraBoom)
	{
		const FRotator BoomRotation = CameraBoom->GetComponentRotation();
		MovementRightVector = BoomRotation.RotateVector(FVector::RightVector);
		MovementUpVector = BoomRotation.RotateVector(FVector::UpVector);
		MovementDepthVector = BoomRotation.RotateVector(FVector::ForwardVector);
	}

	// Flatten the movement axes onto the 2D play plane so no depth component
	// can leak into movement, then renormalise.
	MovementRightVector.Y = 0.0f;
	MovementUpVector.Y = 0.0f;

	MovementRightVector = MovementRightVector.GetSafeNormal(
		UE_SMALL_NUMBER, PTKCharacterDefaults::FallbackScreenRight);
	MovementUpVector = MovementUpVector.GetSafeNormal(
		UE_SMALL_NUMBER, PTKCharacterDefaults::FallbackScreenUp);
	MovementDepthVector = MovementDepthVector.GetSafeNormal(
		UE_SMALL_NUMBER, PTKCharacterDefaults::FallbackScreenDepth);
}

void APTKTopDownCharacter::SetFacingDirection(EPTKFacingDirection NewDirection)
{
	FacingDirection = NewDirection;
	UpdateAnimation();
}

void APTKTopDownCharacter::Input_Move(const FInputActionValue& Value)
{
	const FVector2D Raw = Value.Get<FVector2D>();

	// Logs exactly what Enhanced Input delivered, before any clamping. This is
	// the quickest way to tell an input-mapping fault (wrong or missing
	// modifiers on IMC_PTK_Default) apart from a movement-code fault.
	if (bShowDebugState)
	{
		UE_LOG(LogPTK, Verbose, TEXT("%s IA_Move raw = (%+.2f, %+.2f)"),
			*GetName(), Raw.X, Raw.Y);
	}

	SetMoveInput(Raw);
}

void APTKTopDownCharacter::Input_MoveCompleted(const FInputActionValue& /*Value*/)
{
	// Clears movement but deliberately leaves FacingDirection untouched.
	MoveInput = FVector2D::ZeroVector;
}

void APTKTopDownCharacter::Input_Attack(const FInputActionValue& /*Value*/)
{
	StartAttack();
}

bool APTKTopDownCharacter::StartAttack()
{
	if (MovementState == EPTKMovementState::Dead)
	{
		return false;
	}

	if (MovementState == EPTKMovementState::Attack && !bAllowAttackInterrupt)
	{
		return false;
	}

	// The direction is captured up front - step 1 of the playback contract -
	// so the swing is committed to one direction before anything else runs.
	const EPTKFacingDirection Direction = FacingDirection;
	UPaperFlipbook* const Attack = AttackFlipbooks.GetForDirection(Direction);
	if (!Attack)
	{
		// Refusing here rather than entering the state is deliberate: a
		// character with no attack art must keep walking normally, not freeze
		// for the duration of an animation that will never play.
		UE_LOG(LogPTK, Verbose,
			TEXT("%s cannot attack facing %s - no attack flipbook assigned."),
			*GetName(), *UPTKTypesLibrary::DirectionToString(Direction));
		return false;
	}

	const float Rate = FMath::Max(AttackPlayRate, KINDA_SMALL_NUMBER);
	const float Length = Attack->GetTotalDuration();
	AttackTimeRemaining = (Length > KINDA_SMALL_NUMBER)
		? (Length / Rate)
		: AttackFallbackDuration;
	AttackDuration = AttackTimeRemaining;

	// A fresh swing forgets who the last one hit, so a second attack on the
	// same target connects again - while the set still blocks a single swing
	// from landing twice.
	AttackHitActors.Reset();
	bAttackImpactApplied = false;

	AttackFacingDirection = Direction;
	FacingDirection = Direction;
	MovementState = EPTKMovementState::Attack;

	// Restart from frame 1 even if the same flipbook is already assigned -
	// UpdateAnimation() only rewinds when the asset changes, and attacking
	// twice in the same direction must replay the swing, not resume it.
	if (Sprite)
	{
		Sprite->SetFlipbook(Attack);
		Sprite->SetPlaybackPosition(0.0f, false);
		Sprite->Play();
	}

	UpdateAnimation();
	return true;
}

bool APTKTopDownCharacter::TickAttack(float DeltaSeconds)
{
	if (MovementState != EPTKMovementState::Attack)
	{
		return false;
	}

	if (bLockFacingDuringAttack)
	{
		FacingDirection = AttackFacingDirection;
	}

	AttackTimeRemaining -= DeltaSeconds;

	// Damage is tied to the animation, not to the key press: the swing only
	// connects once it has actually reached its impact pose (frame 5 of 8).
	if (!bAttackImpactApplied && AttackDuration > KINDA_SMALL_NUMBER)
	{
		const float Elapsed = AttackDuration - AttackTimeRemaining;
		if (Elapsed >= AttackDuration * AttackImpactFraction)
		{
			bAttackImpactApplied = true;
			PerformAttackHit();
		}
	}

	if (AttackTimeRemaining > 0.0f)
	{
		return true;
	}

	// Finished. Leave the state cleanly and let this same Tick pick the
	// correct follow-on state from the player's current input.
	AttackTimeRemaining = 0.0f;
	MovementState = EPTKMovementState::Idle;
	return false;
}

UPaperFlipbook* APTKTopDownCharacter::SelectFlipbook_Implementation(
	EPTKMovementState State, EPTKFacingDirection Direction) const
{
	switch (State)
	{
	case EPTKMovementState::Dead:
		// One non-directional collapse. Null is a valid answer: UpdateAnimation
		// then keeps whatever is already on screen, freezing the last living
		// pose rather than blanking the character.
		return DeathFlipbook;

	case EPTKMovementState::Attack:
		return AttackFlipbooks.GetForDirection(Direction);

	case EPTKMovementState::Walk:
		return WalkFlipbooks.GetForDirection(Direction);

	case EPTKMovementState::Idle:
	default:
		return IdleFlipbooks.GetForDirection(Direction);
	}
}

void APTKTopDownCharacter::UpdateAnimation()
{
	if (!Sprite)
	{
		return;
	}

	UPaperFlipbook* const Desired = SelectFlipbook(MovementState, FacingDirection);

	// A missing slot keeps whatever is already playing. Blanking the sprite
	// would make an unassigned flipbook look like the character vanished.
	if (Desired && Sprite->GetFlipbook() != Desired)
	{
		// Turning while walking should continue the stride, not restart it.
		const bool bCarryPhase =
			bPreserveWalkCyclePhase &&
			MovementState == EPTKMovementState::Walk &&
			PreviousMovementState == EPTKMovementState::Walk;

		const float OldPosition = Sprite->GetPlaybackPosition();

		Sprite->SetFlipbook(Desired);

		float NewPosition = 0.0f;
		if (bCarryPhase)
		{
			const float NewLength = Sprite->GetFlipbookLength();
			if (NewLength > KINDA_SMALL_NUMBER)
			{
				NewPosition = FMath::Fmod(OldPosition, NewLength);
			}
		}

		Sprite->SetPlaybackPosition(NewPosition, false);
		Sprite->Play();
	}

	float DesiredRate = IdlePlayRate;
	switch (MovementState)
	{
	case EPTKMovementState::Attack: DesiredRate = AttackPlayRate; break;
	case EPTKMovementState::Walk:   DesiredRate = WalkPlayRate;   break;
	default:                        DesiredRate = IdlePlayRate;   break;
	}

	if (!FMath::IsNearlyEqual(AppliedPlayRate, DesiredRate))
	{
		Sprite->SetPlayRate(DesiredRate);
		AppliedPlayRate = DesiredRate;
	}

	// An attack is a one-shot: it must hold its final pose if the state
	// outlives the flipbook by a frame, never snap back to the wind-up.
	// Idle and Walk are cycles and always loop.
	Sprite->SetLooping(MovementState != EPTKMovementState::Attack);

	PreviousMovementState = MovementState;
}

void APTKTopDownCharacter::UpdateDepthSorting()
{
	if (!Sprite)
	{
		return;
	}

	// A character standing lower on screen must draw in front of one standing
	// higher up - the depth cue a three-quarter view depends on.
	//
	// Pushing along the camera's forward vector scaled by height does that for
	// ANY camera orientation: lower on screen (smaller Z) yields a smaller
	// offset along forward, which leaves the sprite nearer the camera. Writing
	// this as a raw +Y offset would silently invert if the rig is flipped.
	//
	// Under an orthographic projection this offset causes no parallax and no
	// size change - it only reorders what draws on top.
	FVector Desired = SpriteRelativeLocation;
	if (bEnableDepthSorting)
	{
		Desired += MovementDepthVector * (GetActorLocation().Z * DepthSortScale);
	}

	if (!Sprite->GetRelativeLocation().Equals(Desired, 0.01f))
	{
		Sprite->SetRelativeLocation(Desired);
	}
}

void APTKTopDownCharacter::ApplyCollisionAndSpriteSettings()
{
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCapsuleSize(CollisionRadius, CollisionHalfHeight, true);
	}

	if (Sprite)
	{
		Sprite->SetUsingAbsoluteRotation(bLockSpriteWorldRotation);
		Sprite->SetRelativeRotation(FRotator::ZeroRotator);
		Sprite->SetRelativeLocation(SpriteRelativeLocation);
		Sprite->SetRelativeScale3D(
			FVector(PTKCharacterDefaults::SpriteMirrorScaleX, 1.0f, 1.0f));
		Sprite->SetLooping(true);
	}

	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->MaxFlySpeed = MaxMoveSpeed;
		Move->MaxAcceleration = MoveAcceleration;
		Move->BrakingDecelerationFlying = MoveDeceleration;
	}

	if (CameraBoom)
	{
		CameraBoom->TargetArmLength = CameraDistance;
		CameraBoom->bEnableCameraLag = bUseCameraLag;
		CameraBoom->CameraLagSpeed = CameraLagSpeed;
	}

	if (TopDownCamera)
	{
		TopDownCamera->SetOrthoWidth(CameraOrthoWidth);
	}
}

void APTKTopDownCharacter::NotifyControllerChanged()
{
	Super::NotifyControllerChanged();

	AddDefaultMappingContext();
}

void APTKTopDownCharacter::SetupPlayerInputComponent(UInputComponent* PlayerInputComponent)
{
	Super::SetupPlayerInputComponent(PlayerInputComponent);

	if (UEnhancedInputComponent* EnhancedInput = Cast<UEnhancedInputComponent>(PlayerInputComponent))
	{
		if (MoveAction)
		{
			EnhancedInput->BindAction(MoveAction, ETriggerEvent::Triggered, this, &APTKTopDownCharacter::Input_Move);
			EnhancedInput->BindAction(MoveAction, ETriggerEvent::Completed, this, &APTKTopDownCharacter::Input_MoveCompleted);
			EnhancedInput->BindAction(MoveAction, ETriggerEvent::Canceled, this, &APTKTopDownCharacter::Input_MoveCompleted);
		}
		else
		{
			UE_LOG(LogPTK, Warning,
				TEXT("%s has no MoveAction assigned - set it to IA_Move in the character Blueprint."),
				*GetName());
		}

		// Started, not Triggered: one swing per press. Triggered fires every
		// frame the key is held, which would restart the attack continuously.
		if (AttackAction)
		{
			EnhancedInput->BindAction(AttackAction, ETriggerEvent::Started, this, &APTKTopDownCharacter::Input_Attack);
		}
	}
	else
	{
		UE_LOG(LogPTK, Error,
			TEXT("%s did not receive a UEnhancedInputComponent. Check that DefaultInputComponentClass is ")
			TEXT("EnhancedInputComponent in Config/DefaultInput.ini."),
			*GetName());
	}

	AddDefaultMappingContext();
}

void APTKTopDownCharacter::AddDefaultMappingContext()
{
	if (!DefaultMappingContext)
	{
		return;
	}

	const APlayerController* PlayerController = Cast<APlayerController>(GetController());
	if (!PlayerController)
	{
		return;
	}

	if (UEnhancedInputLocalPlayerSubsystem* Subsystem =
			ULocalPlayer::GetSubsystem<UEnhancedInputLocalPlayerSubsystem>(PlayerController->GetLocalPlayer()))
	{
		// AddMappingContext is safe to call more than once for the same context.
		Subsystem->AddMappingContext(DefaultMappingContext, MappingContextPriority);
	}
}

void APTKTopDownCharacter::ValidateFlipbookConfiguration() const
{
	if (!IdleFlipbooks.IsFullyConfigured())
	{
		UE_LOG(LogPTK, Warning,
			TEXT("%s: IdleFlipbooks has %d/4 directions assigned. Missing directions will keep the ")
			TEXT("previous animation instead of updating."),
			*GetName(), IdleFlipbooks.NumConfigured());
	}

	if (!WalkFlipbooks.IsFullyConfigured())
	{
		UE_LOG(LogPTK, Warning,
			TEXT("%s: WalkFlipbooks has %d/4 directions assigned. Missing directions will keep the ")
			TEXT("previous animation instead of updating."),
			*GetName(), WalkFlipbooks.NumConfigured());
	}

	// Partially assigned is the dangerous case and the only one worth warning
	// about: attacking in a direction that has art and then in one that does
	// not looks like the attack randomly failing. Entirely empty is a valid
	// configuration - it simply means this character does not attack.
	const int32 AttackSlots = AttackFlipbooks.NumConfigured();
	if (AttackSlots > 0 && AttackSlots < 4)
	{
		UE_LOG(LogPTK, Warning,
			TEXT("%s: AttackFlipbooks has %d/4 directions assigned. Attacks facing an unassigned ")
			TEXT("direction will be refused."),
			*GetName(), AttackSlots);
	}
}

// ---------------------------------------------------------------------------
// Combat
// ---------------------------------------------------------------------------
bool APTKTopDownCharacter::IsHostileTo(const APTKTopDownCharacter* Other) const
{
	return Other && Other != this && Other->GetTeam() != Team && !Other->IsDead();
}

FVector APTKTopDownCharacter::GetAttackHitCentre() const
{
	// The melee test sits in FRONT of the character, in the direction it is
	// facing on screen. Facing is a flipbook choice, not an actor rotation, so
	// the offset is built from the screen basis rather than from GetActorForwardVector.
	FVector Offset = FVector::ZeroVector;
	switch (FacingDirection)
	{
	case EPTKFacingDirection::Left:  Offset = -MovementRightVector; break;
	case EPTKFacingDirection::Right: Offset =  MovementRightVector; break;
	case EPTKFacingDirection::Up:    Offset =  MovementUpVector;    break;
	case EPTKFacingDirection::Down:
	default:                         Offset = -MovementUpVector;    break;
	}
	return GetActorLocation() + Offset * GetAttackHitDistance();
}

void APTKTopDownCharacter::PerformAttackHit()
{
	UWorld* const World = GetWorld();
	if (!World || AttackDamage <= 0.0f)
	{
		return;
	}

	const FVector Centre = GetAttackHitCentre();

	if (bDrawAttackHit)
	{
		DrawDebugSphere(World, Centre, GetAttackHitRadius(), 16, FColor::Yellow, false, 1.0f);
	}

	// A sphere overlap rather than the sprite bounds. Ravager's axe and cape
	// reach far outside his body; treating the artwork as a hitbox would let
	// him damage things he never swung at.
	TArray<FOverlapResult> Overlaps;
	FCollisionQueryParams Params(SCENE_QUERY_STAT(PTKAttackHit), false, this);
	Params.AddIgnoredActor(this);

	World->OverlapMultiByObjectType(
		Overlaps, Centre, FQuat::Identity,
		FCollisionObjectQueryParams(ECC_Pawn),
		FCollisionShape::MakeSphere(GetAttackHitRadius()), Params);

	for (const FOverlapResult& Result : Overlaps)
	{
		APTKTopDownCharacter* Victim = Cast<APTKTopDownCharacter>(Result.GetActor());
		if (!IsHostileTo(Victim))
		{
			continue;
		}

		// One swing, one hit per victim. AttackHitActors is cleared by
		// StartAttack, so the next swing can damage the same target again.
		bool bAlready = false;
		AttackHitActors.Add(Victim, &bAlready);
		if (bAlready)
		{
			continue;
		}

		if (UPTKHealthComponent* VictimHealth = Victim->GetHealthComponent())
		{
			const float Dealt = VictimHealth->ApplyDamage(AttackDamage, this);
			if (Dealt > 0.0f)
			{
				OnAttackHit(Victim, Dealt);
			}
		}
	}
}

// ---------------------------------------------------------------------------
// Health / death
// ---------------------------------------------------------------------------
void APTKTopDownCharacter::HandleHealthChanged(UPTKHealthComponent* /*Component*/,
	float NewHealth, float Delta, AActor* DamageInstigator)
{
	if (Delta < 0.0f)
	{
		UE_LOG(LogPTK, Verbose, TEXT("%s hit for %.0f by %s (%.0f left)"),
			*GetName(), -Delta, *GetNameSafe(DamageInstigator), NewHealth);
	}
}

void APTKTopDownCharacter::HandleDeathEvent(UPTKHealthComponent* /*Component*/, AActor* Killer)
{
	HandleDeath(Killer);
}

void APTKTopDownCharacter::HandleDeath(AActor* Killer)
{
	if (MovementState == EPTKMovementState::Dead)
	{
		return;
	}

	MovementState = EPTKMovementState::Dead;
	MoveInput = FVector2D::ZeroVector;
	AttackTimeRemaining = 0.0f;

	// Stop dead rather than sliding to a halt: a corpse that keeps its momentum
	// drifts away from where it was killed.
	if (UCharacterMovementComponent* Move = GetCharacterMovement())
	{
		Move->StopMovementImmediately();
		Move->DisableMovement();
	}

	// Collision off so the survivor can walk through the body and no further
	// melee overlap can find it.
	if (UCapsuleComponent* Capsule = GetCapsuleComponent())
	{
		Capsule->SetCollisionEnabled(ECollisionEnabled::NoCollision);
	}

	// Player characters also lose control. Enemies have no controller input to
	// disable, so this is a no-op for them.
	if (APlayerController* PC = Cast<APlayerController>(GetController()))
	{
		DisableInput(PC);
	}

	// Push the collapse directly rather than waiting for UpdateAnimation: Tick
	// returns early once dead, so nothing else would ever start it playing.
	float DeathLength = 0.0f;
	if (Sprite && DeathFlipbook)
	{
		const float Rate = FMath::Max(DeathPlayRate, KINDA_SMALL_NUMBER);
		Sprite->SetFlipbook(DeathFlipbook);
		Sprite->SetPlayRate(Rate);
		// One shot: the corpse must hold its final frame, not loop back to
		// standing up and falling over again.
		Sprite->SetLooping(false);
		Sprite->SetPlaybackPosition(0.0f, false);
		Sprite->Play();
		AppliedPlayRate = Rate;
		DeathLength = DeathFlipbook->GetTotalDuration() / Rate;
	}

	UE_LOG(LogPTK, Log, TEXT("%s entered Dead state (killer: %s, collapse %.2fs)"),
		*GetName(), *GetNameSafe(Killer), DeathLength);

	if (DestroyDelayAfterDeath > 0.0f)
	{
		// The player is deliberately NOT destroyed: the defeat state has to stay
		// on screen. Only AI corpses are cleaned up, and only after the collapse
		// has finished playing - otherwise they pop out mid-fall.
		if (!Cast<APlayerController>(GetController()))
		{
			SetLifeSpan(DeathLength + DestroyDelayAfterDeath);
		}
	}
}
